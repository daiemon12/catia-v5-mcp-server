#ifndef CatiaPyBridgePointDemo_h
#define CatiaPyBridgePointDemo_h

#include "CATSysErrorDef.h"
#include "CatiaPyBridgeRequest.h"
#include "CatiaPyBridgeResponse.h"

// Educational extension. Execute only through the existing main-thread Bridge.
class CatiaPyBridgePointDemo
{
public:
    static HRESULT CreatePoint(const CatiaPyBridgeRequest& request,
                               CatiaPyBridgeResponse& response);
};

#endif
