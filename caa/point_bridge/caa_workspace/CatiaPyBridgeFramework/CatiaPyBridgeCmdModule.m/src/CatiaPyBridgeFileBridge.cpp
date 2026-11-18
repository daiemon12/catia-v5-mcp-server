#include "CatiaPyBridgeFileBridge.h"
#include "CatiaPyBridgeJson.h"

#include <fstream>
#include <sstream>
#include <windows.h>

namespace
{
const wchar_t* const BridgeRoot = L"CATIA_MCP_CAA_BRIDGE_ROOT";

bool IsJobId(const std::string& id)
{
    return id.size() == 32 && id.find_first_not_of("0123456789abcdef") == std::string::npos;
}

std::wstring JobFile(
    const std::wstring& root, const wchar_t* directory, const std::string& id,
    const wchar_t* suffix)
{
    return root + directory + std::wstring(id.begin(), id.end()) + suffix;
}

bool EnsureDirectory(const std::wstring& path)
{
    if (CreateDirectoryW(path.c_str(), NULL))
        return true;
    if (GetLastError() != ERROR_ALREADY_EXISTS)
        return false;
    const DWORD attributes = GetFileAttributesW(path.c_str());
    return attributes != INVALID_FILE_ATTRIBUTES && (attributes & FILE_ATTRIBUTE_DIRECTORY);
}

bool IsMissing(const std::wstring& path)
{
    if (GetFileAttributesW(path.c_str()) != INVALID_FILE_ATTRIBUTES)
        return false;
    const DWORD error = GetLastError();
    return error == ERROR_FILE_NOT_FOUND || error == ERROR_PATH_NOT_FOUND;
}

bool ReadObject(const std::wstring& path, nlohmann::json& object)
{
    std::ifstream input(path.c_str(), std::ios::binary);
    if (!input)
        return false;
    std::ostringstream buffer;
    buffer << input.rdbuf();
    return !input.bad() && CatiaPyBridgeJson::ParseObject(buffer.str(), object);
}
}

CatiaPyBridgeFileBridge::CatiaPyBridgeFileBridge()
    : _rootDir(RootDirectory())
{
}

std::wstring CatiaPyBridgeFileBridge::RootDirectory()
{
    const DWORD size = GetEnvironmentVariableW(BridgeRoot, NULL, 0);
    if (size == 0)
        return std::wstring();

    std::wstring root(size, L'\0');
    const DWORD length = GetEnvironmentVariableW(BridgeRoot, &root[0], size);
    if (length == 0 || length >= size)
        return std::wstring();
    root.resize(length);
    return root;
}

HRESULT CatiaPyBridgeFileBridge::EnsureDirectories() const
{
    if (_rootDir.empty() || !EnsureDirectory(_rootDir))
        return E_FAIL;
    const wchar_t* directories[] = {
        L"\\pending", L"\\requests", L"\\responses", L"\\done", L"\\logs"
    };
    for (const wchar_t* directory : directories)
        if (!EnsureDirectory(_rootDir + directory))
            return E_FAIL;
    return S_OK;
}

HRESULT CatiaPyBridgeFileBridge::ReadCurrentJob(CatiaPyBridgeRequest& request) const
{
    nlohmann::json job;
    std::string id;
    if (!ReadObject(_rootDir + L"\\pending\\current_job.json", job) ||
        !CatiaPyBridgeJson::GetStringValue(job, "job_id", id) || !IsJobId(id))
    {
        request.SetError("INVALID_CURRENT_JOB", "Missing or invalid job descriptor");
        return E_FAIL;
    }

    if (!IsMissing(JobFile(_rootDir, L"\\responses\\", id, L".response.json")) ||
        !IsMissing(JobFile(_rootDir, L"\\done\\", id, L".response.json")))
    {
        request.SetError("CAA_ALREADY_COMPLETED", "Job response already exists or cannot be inspected");
        return E_FAIL;
    }

    request.JobId = id;
    return S_OK;
}

HRESULT CatiaPyBridgeFileBridge::ReadRequest(CatiaPyBridgeRequest& request) const
{
    nlohmann::json message;
    std::string id;
    if (!ReadObject(JobFile(_rootDir, L"\\requests\\", request.JobId, L".request.json"), message) ||
        !CatiaPyBridgeJson::GetStringValue(message, "id", id) || id != request.JobId ||
        !CatiaPyBridgeJson::GetStringValue(message, "method", request.Method) ||
        request.Method.empty())
    {
        request.SetError("INVALID_REQUEST", "Invalid or uncorrelated request");
        return E_FAIL;
    }

    const auto parameters = message.find("params");
    if (parameters == message.end() || !parameters->is_object())
    {
        request.SetError("INVALID_REQUEST", "Request params must be a JSON object");
        return E_FAIL;
    }

    request.Params = *parameters;
    return S_OK;
}

HRESULT CatiaPyBridgeFileBridge::WriteResponse(const CatiaPyBridgeResponse& response) const
{
    if (!IsJobId(response.JobId))
        return E_FAIL;

    const std::wstring path = JobFile(_rootDir, L"\\responses\\", response.JobId, L".response.json");
    const std::wstring temporary = path + L".tmp";
    {
        std::ofstream output(temporary.c_str(), std::ios::binary | std::ios::trunc);
        output << CatiaPyBridgeJson::BuildResponseJson(response);
        output.close();
        if (!output)
        {
            DeleteFileW(temporary.c_str());
            return E_FAIL;
        }
    }

    if (!MoveFileExW(temporary.c_str(), path.c_str(), MOVEFILE_WRITE_THROUGH))
    {
        DeleteFileW(temporary.c_str());
        return E_FAIL;
    }
    return S_OK;
}
