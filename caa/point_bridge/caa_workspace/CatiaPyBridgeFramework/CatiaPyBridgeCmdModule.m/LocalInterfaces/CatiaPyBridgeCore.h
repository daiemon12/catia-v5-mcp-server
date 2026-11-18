#ifndef CatiaPyBridgeCore_H
#define CatiaPyBridgeCore_H
#include "CatiaPyBridgeRequest.h"
#include "CatiaPyBridgeResponse.h"
class CatiaPyBridgeCore
{
public:
    static HRESULT Execute(const CatiaPyBridgeRequest&, CatiaPyBridgeResponse&);
};
#endif
