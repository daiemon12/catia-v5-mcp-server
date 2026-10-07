#include "CatiaPyBridgeFileBridge.h"
#include "CatiaPyBridgeJson.h"
#include "CatiaPyBridgeLogger.h"

#include <cstdlib>
#include <fstream>
#include <sstream>
#include <windows.h>

CatiaPyBridgeFileBridge::CatiaPyBridgeFileBridge()
    : _rootDir("")
{
    const char* temp = std::getenv("TEMP");
    if (temp == NULL || temp[0] == '\0')
        temp = std::getenv("TMP");
    if (temp == NULL || temp[0] == '\0')
        _rootDir = ".\\CatiaPyBridge";
    else
        _rootDir = JoinPath(temp, "CatiaPyBridge");
}

std::string CatiaPyBridgeFileBridge::JoinPath(
    const std::string& left,
    const std::string& right)
{
    if (left.empty())
        return right;
    const char last = left[left.size() - 1];
    if (last == '\\' || last == '/')
        return left + right;
    return left + "\\" + right;
}

HRESULT CatiaPyBridgeFileBridge::EnsureDirectory(const std::string& path)
{
    if (CreateDirectoryA(path.c_str(), NULL) || GetLastError() == ERROR_ALREADY_EXISTS)
        return S_OK;
    return E_FAIL;
}

HRESULT CatiaPyBridgeFileBridge::EnsureDirectories()
{
    if (FAILED(EnsureDirectory(_rootDir)))
        return E_FAIL;
    if (FAILED(EnsureDirectory(JoinPath(_rootDir, "pending"))))
        return E_FAIL;
    if (FAILED(EnsureDirectory(JoinPath(_rootDir, "requests"))))
        return E_FAIL;
    if (FAILED(EnsureDirectory(JoinPath(_rootDir, "responses"))))
        return E_FAIL;
    if (FAILED(EnsureDirectory(JoinPath(_rootDir, "done"))))
        return E_FAIL;
    if (FAILED(EnsureDirectory(JoinPath(_rootDir, "logs"))))
        return E_FAIL;
    return S_OK;
}

bool CatiaPyBridgeFileBridge::ReadTextFile(
    const std::string& path,
    std::string& content)
{
    std::ifstream in(path.c_str(), std::ios::in | std::ios::binary);
    if (!in)
        return false;

    std::ostringstream buffer;
    buffer << in.rdbuf();
    content = buffer.str();
    return true;
}

HRESULT CatiaPyBridgeFileBridge::WriteTextFileAtomic(
    const std::string& path,
    const std::string& content)
{
    const std::string tmpPath = path + ".tmp";
    {
        std::ofstream out(tmpPath.c_str(), std::ios::out | std::ios::binary | std::ios::trunc);
        if (!out)
            return E_FAIL;
        out << content;
        out.flush();
        if (!out)
            return E_FAIL;
    }

    if (!MoveFileExA(
            tmpPath.c_str(),
            path.c_str(),
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH))
    {
        DeleteFileA(tmpPath.c_str());
        return E_FAIL;
    }

    return S_OK;
}

HRESULT CatiaPyBridgeFileBridge::ReadCurrentJob(CatiaPyBridgeRequest& request)
{
    const std::string currentPath = JoinPath(JoinPath(_rootDir, "pending"), "current_job.json");
    return ReadJobFile(currentPath, request);
}

HRESULT CatiaPyBridgeFileBridge::ReadJobFile(
    const std::string& jobPath,
    CatiaPyBridgeRequest& request)
{
    CatiaPyBridgeLogger::Info("read job path=" + jobPath);

    std::string json;
    if (!ReadTextFile(jobPath, json))
    {
        request.SetError("INVALID_CURRENT_JOB", "job descriptor was not found", jobPath);
        return E_FAIL;
    }

    if (!CatiaPyBridgeJson::GetStringValue(json, "job_id", request.JobId) ||
        !CatiaPyBridgeJson::GetStringValue(json, "request_path", request.RequestPath) ||
        !CatiaPyBridgeJson::GetStringValue(json, "response_path", request.ResponsePath))
    {
        request.SetError("INVALID_CURRENT_JOB", "job descriptor is missing job_id, request_path, or response_path", jobPath);
        return E_FAIL;
    }

    return S_OK;
}

HRESULT CatiaPyBridgeFileBridge::ReadRequest(CatiaPyBridgeRequest& request)
{
    if (request.RequestPath.empty())
    {
        request.SetError("INVALID_REQUEST", "request_path is empty");
        return E_FAIL;
    }

    CatiaPyBridgeLogger::Info("read request path=" + request.RequestPath);
    std::string json;
    if (!ReadTextFile(request.RequestPath, json))
    {
        request.SetError("REQUEST_NOT_FOUND", "request.json was not found", request.RequestPath);
        return E_FAIL;
    }

    std::string id;
    if (!CatiaPyBridgeJson::GetStringValue(json, "id", id) ||
        !CatiaPyBridgeJson::GetStringValue(json, "method", request.Method))
    {
        request.SetError("INVALID_REQUEST", "request.json is missing id or method", request.RequestPath);
        return E_FAIL;
    }

    if (id != request.JobId)
    {
        request.SetError("INVALID_REQUEST", "request id does not match current job id", id);
        return E_FAIL;
    }

    if (request.Method.empty())
    {
        request.SetError("INVALID_REQUEST", "request method is empty", request.RequestPath);
        return E_FAIL;
    }

    if (!CatiaPyBridgeJson::GetObjectRaw(json, "params", request.ParamsJson))
        request.ParamsJson = "{}";

    return S_OK;
}

HRESULT CatiaPyBridgeFileBridge::WriteResponse(const CatiaPyBridgeResponse& response)
{
    if (response.ResponsePath.empty())
    {
        CatiaPyBridgeLogger::Error("response path is empty");
        return E_FAIL;
    }

    const std::string payload = CatiaPyBridgeJson::BuildResponseJson(response);
    const HRESULT hr = WriteTextFileAtomic(response.ResponsePath, payload);
    if (FAILED(hr))
    {
        CatiaPyBridgeLogger::Error("WRITE_RESPONSE_FAILED path=" + response.ResponsePath);
        return E_FAIL;
    }

    CatiaPyBridgeLogger::Info("wrote response path=" + response.ResponsePath);
    return S_OK;
}

HRESULT CatiaPyBridgeFileBridge::WriteDoneMarker(const CatiaPyBridgeResponse& response)
{
    if (response.JobId.empty() || response.JobId == "unknown")
        return S_OK;

    const std::string donePath = JoinPath(JoinPath(_rootDir, "done"), response.JobId + ".done.json");
    std::ostringstream payload;
    payload << "{\n";
    payload << "  \"id\": \"" << CatiaPyBridgeJson::Escape(response.JobId) << "\",\n";
    payload << "  \"ok\": " << (response.Ok ? "true" : "false") << "\n";
    payload << "}\n";
    return WriteTextFileAtomic(donePath, payload.str());
}

std::string CatiaPyBridgeFileBridge::GetRootDir() const
{
    return _rootDir;
}

std::string CatiaPyBridgeFileBridge::GetLogDir() const
{
    return JoinPath(_rootDir, "logs");
}
