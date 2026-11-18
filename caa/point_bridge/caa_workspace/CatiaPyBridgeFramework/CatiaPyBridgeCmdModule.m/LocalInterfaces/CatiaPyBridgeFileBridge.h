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

    HRESULT EnsureDirectories() const;
    HRESULT ReadCurrentJob(CatiaPyBridgeRequest& request) const;
    HRESULT ReadRequest(CatiaPyBridgeRequest& request) const;
    HRESULT WriteResponse(const CatiaPyBridgeResponse& response) const;

    static std::wstring RootDirectory();

private:
    std::wstring _rootDir;
};

#endif
