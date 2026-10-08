#ifndef CatiaPyBridgeFileBridge_H
#define CatiaPyBridgeFileBridge_H

#include "CATSysErrorDef.h"
#include "CatiaPyBridgeRequest.h"
#include "CatiaPyBridgeResponse.h"

#include <string>

class CatiaPyBridgeFileBridge
{
public:
    CatiaPyBridgeFileBridge();

    HRESULT EnsureDirectories();
    HRESULT ReadCurrentJob(CatiaPyBridgeRequest& request);
    HRESULT ReadJobFile(const std::string& jobPath, CatiaPyBridgeRequest& request);
    HRESULT ReadRequest(CatiaPyBridgeRequest& request);
    HRESULT WriteResponse(const CatiaPyBridgeResponse& response);
    HRESULT WriteDoneMarker(const CatiaPyBridgeResponse& response);

    std::string GetRootDir() const;
    std::string GetLogDir() const;

private:
    std::string _rootDir;

    static bool ReadTextFile(const std::string& path, std::string& content);
    static HRESULT WriteTextFileAtomic(const std::string& path, const std::string& content);
    static std::string JoinPath(const std::string& left, const std::string& right);
    static HRESULT EnsureDirectory(const std::string& path);
};

#endif
