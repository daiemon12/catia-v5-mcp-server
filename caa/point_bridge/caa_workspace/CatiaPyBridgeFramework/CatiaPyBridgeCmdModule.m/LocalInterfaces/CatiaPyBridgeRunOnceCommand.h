#ifndef CatiaPyBridgeRunOnceCommand_H
#define CatiaPyBridgeRunOnceCommand_H

#include "CATCommand.h"
#include "CATSysErrorDef.h"

class CatiaPyBridgeRunOnceCommand : public CATCommand
{
public:
    CatiaPyBridgeRunOnceCommand();
    virtual ~CatiaPyBridgeRunOnceCommand();

    virtual CATStatusChangeRC Activate(
        CATCommand* iFromClient,
        CATNotification* iNotification);
    virtual CATStatusChangeRC Desactivate(
        CATCommand* iFromClient,
        CATNotification* iNotification);
    virtual CATStatusChangeRC Cancel(
        CATCommand* iFromClient,
        CATNotification* iNotification);

private:
    static HRESULT ExecuteBridgeJob();
    int _executed;
};

#endif
