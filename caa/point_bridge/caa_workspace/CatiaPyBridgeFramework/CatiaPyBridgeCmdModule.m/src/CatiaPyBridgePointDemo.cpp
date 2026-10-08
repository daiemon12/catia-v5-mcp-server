#include "CatiaPyBridgePointDemo.h"
#include "CatiaPyBridgeJson.h"

#include "CATDocument.h"
#include "CATFrmEditor.h"
#include "CATInit.h"
#include "CATIPrtContainer.h"
#include "CATIADocument.h"
#include "CATIAlias.h"
#include "CATIPartRequest.h"
#include "CATIGSMTool.h"
#include "CATIGSMFactory.h"
#include "CATIGSMPointCoord.h"
#include "CATIGSMProceduralView.h"
#include "CATICkeParmFactory.h"
#include "CATICkeParm.h"
#include "CATICkeInst.h"
#include "CATIDescendants.h"
#include "CATISpecObject.h"
#include "CATLISTV_CATBaseUnknown.h"
#include "CATError.h"
#include "CATErrorMacros.h"

#include <windows.h>
#include <cmath>
#include <ctime>
#include <iomanip>
#include <limits>
#include <map>
#include <sstream>
#include <vector>

namespace
{
std::string Utf8(const CATUnicodeString& value)
{
    size_t size = static_cast<size_t>(value.GetLengthInChar()) * 4;
    std::vector<char> buffer(size + 1, '\0');
    value.ConvertToUTF8(&buffer[0], &size);
    return std::string(&buffer[0], size);
}
CATUnicodeString Unicode(const std::string& value)
{
    CATUnicodeString result;
    result.BuildFromUTF8(value.c_str(), value.size());
    return result;
}
std::string Quote(const std::string& value)
{
    return "\"" + CatiaPyBridgeJson::Escape(value) + "\"";
}
std::string Alias(const CATISpecObject_var& spec)
{
    CATIAlias_var alias = spec;
    return alias == NULL_var ? Utf8(spec->GetName()) : Utf8(alias->GetAlias());
}
std::string PathKey(std::string path)
{
    for (size_t i = 0; i < path.size(); ++i)
    {
        if (path[i] == '\\') path[i] = '/';
        if (path[i] >= 'A' && path[i] <= 'Z') path[i] += 'a' - 'A';
    }
    return path;
}
// Correlation digest only. Execution also compares the FULL plan and state.
std::string Digest(const std::string& material)
{
    unsigned long hash = 2166136261UL;
    for (size_t i = 0; i < material.size(); ++i)
        hash = (hash ^ static_cast<unsigned char>(material[i])) * 16777619UL;
    std::ostringstream out;
    out << std::hex << std::setw(8) << std::setfill('0') << hash;
    return out.str();
}
struct Preview
{
    std::string material;
    std::time_t expires;
};
// No CAA object or interface pointer survives a request.
std::map<std::string, Preview> previews;
unsigned long pointPreviewSequence = 0;
void Prune()
{
    const std::time_t now = std::time(NULL);
    for (std::map<std::string, Preview>::iterator i = previews.begin(); i != previews.end();)
        if (i->second.expires <= now) previews.erase(i++); else ++i;
    while (previews.size() >= 32) previews.erase(previews.begin());
}
HRESULT Fail(CatiaPyBridgeResponse& response, const char* code,
             const std::string& message, const std::string& stage,
             bool modified = false)
{
    response.SetError(code, message, "{\"failure_stage\":" + Quote(stage) +
        ",\"modified\":" + (modified ? "true" : "false") +
        ",\"saved\":false,\"automatic_retry_allowed\":false}");
    return S_OK;
}
}

HRESULT CatiaPyBridgePointDemo::CreatePoint(const CatiaPyBridgeRequest& request,
                                          CatiaPyBridgeResponse& response)
{
    std::string path, targetName, pointName, suppliedPlan, suppliedState, token;
    CatiaPyBridgeJson::GetStringValue(request.ParamsJson, "part_document_path", path);
    CatiaPyBridgeJson::GetStringValue(request.ParamsJson, "geometrical_set_name", targetName);
    CatiaPyBridgeJson::GetStringValue(request.ParamsJson, "point_name", pointName);
    CatiaPyBridgeJson::GetStringValue(request.ParamsJson, "plan_hash", suppliedPlan);
    CatiaPyBridgeJson::GetStringValue(request.ParamsJson, "state_fingerprint", suppliedState);
    CatiaPyBridgeJson::GetStringValue(request.ParamsJson, "confirmed_preview_token", token);
    const bool dryRun = CatiaPyBridgeJson::GetBoolValue(request.ParamsJson, "dry_run", true);
    const bool confirmed = CatiaPyBridgeJson::GetBoolValue(request.ParamsJson, "confirm_action", false);
    const double missing = std::numeric_limits<double>::quiet_NaN();
    double coordinates[3];
    coordinates[0] = CatiaPyBridgeJson::GetDoubleValue(request.ParamsJson, "x_mm", missing);
    coordinates[1] = CatiaPyBridgeJson::GetDoubleValue(request.ParamsJson, "y_mm", missing);
    coordinates[2] = CatiaPyBridgeJson::GetDoubleValue(request.ParamsJson, "z_mm", missing);
    if (path.empty() || targetName.empty() || pointName.empty() ||
        pointName.find("MCP_") == 0 || pointName.find("CatiaPyBridge_") == 0)
        return Fail(response, "CAA_INVALID_ARGUMENT", "Explicit path, set and engineering point name are required", "validate");
    for (int i = 0; i < 3; ++i)
        if (!(coordinates[i] >= -1000000.0 && coordinates[i] <= 1000000.0))
            return Fail(response, "CAA_INVALID_ARGUMENT", "Coordinates must be finite and within +/-1000000 mm", "validate");
    if (!dryRun && !confirmed)
        return Fail(response, "CAA_CONFIRM_REQUIRED", "Execution requires confirm_action=true after preview", "confirm");

    CATFrmEditor* editor = CATFrmEditor::GetCurrentEditor();
    if (editor == NULL || editor->GetDocument() == NULL)
        return Fail(response, "CAA_NO_ACTIVE_DOCUMENT", "No active document", "document");
    CATDocument* document = editor->GetDocument();
    const double requestedPid = CatiaPyBridgeJson::GetDoubleValue(request.ParamsJson, "catia_process_id", 0);
    if (requestedPid != static_cast<double>(GetCurrentProcessId()))
        return Fail(response, "CAA_PROCESS_MISMATCH", "Exact CNEXT PID differs from the requested instance", "document");
    const std::string actualPath = Utf8(document->StorageName());
    if (PathKey(actualPath) != PathKey(path))
        return Fail(response, "CAA_DOCUMENT_MISMATCH", "Active saved document path differs from the explicit target", "document");

    CATIADocument* automationDocument = NULL;
    const HRESULT documentInterfaceHr = document->QueryInterface(IID_CATIADocument, (void**)&automationDocument);
    CAT_VARIANT_BOOL readOnly = 0;
    HRESULT accessHr = E_FAIL;
    if (SUCCEEDED(documentInterfaceHr) && automationDocument != NULL)
        accessHr = automationDocument->get_ReadOnly(readOnly);
    if (automationDocument != NULL) automationDocument->Release();
    if (FAILED(accessHr))
        return Fail(response, "CAA_DOCUMENT_STATE_UNAVAILABLE", "Cannot read document write access", "document");
    if (readOnly)
        return Fail(response, "CAA_READ_ONLY_DOCUMENT", "Target document is read-only", "document");

    CATInit_var init = document;
    if (init == NULL_var)
        return Fail(response, "CAA_WRONG_DOCUMENT_TYPE", "Target is not a Part", "document");
    CATIPrtContainer* container = (CATIPrtContainer*)init->GetRootContainer("CATIPrtContainer");
    if (container == NULL)
        return Fail(response, "CAA_WRONG_DOCUMENT_TYPE", "Target has no Part specification container", "document");
    CATISpecObject_var part = container->GetPart();
    CATIGSMFactory_var geometryFactory = container;
    CATICkeParmFactory_var parameterFactory = container;
    container->Release();
    CATIPartRequest_var partRequest = part;
    if (partRequest == NULL_var || geometryFactory == NULL_var || parameterFactory == NULL_var)
        return Fail(response, "CAA_FACTORY_UNAVAILABLE", "Part/GSM/Knowledge factory unavailable; check licenses", "factory");

    CATListValCATBaseUnknown_var bodies;
    if (FAILED(partRequest->GetDirectBodies("MfDefault3DView", bodies)) || bodies.Size() > 128)
        return Fail(response, "CAA_SCOPE_LIMIT", "Cannot read bounded root body inventory (max 128)", "target");
    CATISpecObject_var target;
    int matches = 0;
    int targetIndex = 0;
    for (int i = 1; i <= bodies.Size(); ++i)
    {
        CATISpecObject_var candidate = bodies[i];
        CATIGSMTool_var tool = candidate;
        if (candidate != NULL_var && tool != NULL_var && Alias(candidate) == targetName)
        {
            target = candidate;
            targetIndex = i;
            ++matches;
        }
    }
    if (matches != 1)
        return Fail(response, matches ? "CAA_TARGET_AMBIGUOUS" : "CAA_TARGET_NOT_FOUND",
            "Expected exactly one root Geometrical Set with the requested name", "target");
    CATIGSMTool_var targetTool = target;
    int toolType = -1;
    int privateMode = -1;
    if (FAILED(targetTool->GetType(toolType)) || toolType != 0 ||
        SUCCEEDED(targetTool->IsPrivate(privateMode)))
        return Fail(response, "CAA_UNSUPPORTED_TARGET", "Demo accepts only public ordinary root Geometrical Sets", "target");
    CATIDescendants_var children = target;
    if (children == NULL_var || children->GetNumberOfChildren() > 256)
        return Fail(response, "CAA_SCOPE_LIMIT", "Target child inventory unavailable or exceeds 256", "target");

    std::ostringstream state;
    state << Quote(PathKey(actualPath)) << '|' << GetCurrentProcessId() << '|'
          << targetIndex << '|' << Quote(targetName) << '|' << children->GetNumberOfChildren();
    for (int i = 1; i <= children->GetNumberOfChildren(); ++i)
    {
        CATISpecObject_var child = children->GetChildAtPosition(i);
        if (child == NULL_var)
            return Fail(response, "CAA_TARGET_STATE_UNAVAILABLE", "A target child cannot be read", "target");
        if (Alias(child) == pointName)
            return Fail(response, "CAA_NAME_EXISTS", "Point name already exists in the target set", "target");
        state << '|' << i << ':' << Quote(Alias(child)) << ':' << Quote(Utf8(child->GetType()));
    }
    std::ostringstream material;
    material << state.str() << '|' << Quote(pointName) << std::setprecision(17)
             << '|' << coordinates[0] << '|' << coordinates[1] << '|' << coordinates[2];
    const std::string planHash = Digest(material.str());
    const std::string fingerprint = "point-state:" + Digest(state.str());
    Prune();
    if (dryRun)
    {
        std::ostringstream tokenValue;
        tokenValue << "point-preview:" << GetCurrentProcessId() << ':' << ++pointPreviewSequence << ':' << request.JobId;
        Preview preview;
        preview.material = material.str();
        preview.expires = std::time(NULL) + 300;
        previews[tokenValue.str()] = preview;
        std::ostringstream result;
        result << "{\"dry_run\":true,\"created\":false,\"modified\":false,\"saved\":false,"
               << "\"part_document_path\":" << Quote(actualPath)
               << ",\"geometrical_set_name\":" << Quote(targetName)
               << ",\"point_name\":" << Quote(pointName)
               << ",\"coordinates_mm\":[" << std::setprecision(17) << coordinates[0] << ',' << coordinates[1] << ',' << coordinates[2] << ']'
               << ",\"coordinate_system\":\"part_absolute\",\"plan_hash\":" << Quote(planHash)
               << ",\"state_fingerprint\":" << Quote(fingerprint)
               << ",\"confirmed_preview_token\":" << Quote(tokenValue.str())
               << ",\"preview_expires_in_seconds\":300}";
        response.SetSuccess(result.str());
        return S_OK;
    }
    std::map<std::string, Preview>::iterator preview = previews.find(token);
    if (preview == previews.end() || preview->second.material != material.str() ||
        suppliedPlan != planHash || suppliedState != fingerprint)
        return Fail(response, "CAA_PREVIEW_INVALID", "Preview expired, consumed, or target/plan changed", "confirm");
    // Consume BEFORE the first mutation, including failure cases. Never retry a write.
    previews.erase(preview);

    // B30 can use longjmp exceptions: owned interface values live outside CATTry.
    CATICkeParm_var parameters[3], readback[3];
    CATICkeInst_var values[3];
    CATIGSMPointCoord_var point;
    CATISpecObject_var pointSpec;
    CATIGSMProceduralView_var insertion;
    CATIAlias_var pointAlias;
    std::string stage = "create_parameters";
    std::string failure;
    bool modified = false;
    double measured[3] = {0.0, 0.0, 0.0};
    CATTry
    {
        const char* suffixes[3] = {"_X", "_Y", "_Z"};
        for (int i = 0; i < 3 && failure.empty(); ++i)
        {
            modified = true; // Conservative if the factory raises after a partial write.
            parameters[i] = parameterFactory->CreateLength(Unicode(pointName + suffixes[i]), coordinates[i] / 1000.0);
            if (parameters[i] == NULL_var) failure = "CreateLength returned null";
        }
        if (failure.empty())
        {
            stage = "create_point";
            point = geometryFactory->CreatePoint(parameters[0], parameters[1], parameters[2]);
            pointSpec = point;
            pointAlias = point;
            insertion = point;
            if (point == NULL_var || pointSpec == NULL_var || pointAlias == NULL_var || insertion == NULL_var)
                failure = "CreatePoint or required point interfaces unavailable";
        }
        if (failure.empty())
        {
            stage = "name_and_insert";
            pointAlias->SetAlias(Unicode(pointName));
            if (FAILED(point->SetReferencePoint(NULL_var)) || FAILED(point->SetReferenceAxis(NULL_var)) ||
                FAILED(insertion->InsertInProceduralView(children, FALSE)))
                failure = "Absolute reference or explicit target insertion failed";
        }
        if (failure.empty())
        {
            stage = "update";
            pointSpec->Update();
            stage = "readback";
            if (FAILED(point->GetCoordinates(readback[0], readback[1], readback[2])))
                failure = "GetCoordinates failed";
            for (int i = 0; i < 3 && failure.empty(); ++i)
            {
                if (readback[i] == NULL_var) failure = "Coordinate parameter unavailable";
                else
                {
                    values[i] = readback[i]->Value();
                    if (values[i] == NULL_var) failure = "Coordinate value unavailable";
                    else
                    {
                        measured[i] = values[i]->AsReal() * 1000.0;
                        if (!(measured[i] >= -1000000.0 && measured[i] <= 1000000.0) ||
                            std::fabs(measured[i] - coordinates[i]) > 0.000001)
                            failure = "Native coordinate readback differs from the plan";
                    }
                }
            }
            if (failure.empty() && (Alias(pointSpec) != pointName ||
                children->GetNumberOfChildren() < 1 || children->GetPosition(pointSpec) < 1))
                failure = "Point name or target membership readback failed";
        }
    }
    CATCatch(CATError, error)
    {
        failure = Utf8(error->GetNLSMessage());
        if (failure.empty()) failure = "Native CATIA exception";
        delete error;
    }
    CATEndTry;
    if (!failure.empty())
        return Fail(response, "CAA_POINT_CREATE_FAILED", failure, stage, modified);
    std::ostringstream result;
    result << "{\"dry_run\":false,\"created\":true,\"modified\":true,\"updated\":true,\"saved\":false,"
           << "\"part_document_path\":" << Quote(actualPath)
           << ",\"geometrical_set_name\":" << Quote(targetName)
           << ",\"point_name\":" << Quote(pointName)
           << ",\"coordinates_mm\":[" << std::setprecision(17) << measured[0] << ',' << measured[1] << ',' << measured[2] << ']'
           << ",\"coordinate_system\":\"part_absolute\",\"native_readback_complete\":true}";
    response.SetSuccess(result.str());
    return S_OK;
}
