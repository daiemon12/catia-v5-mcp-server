#ifndef CatiaPyBridgeRunOnceCommand_H
#define CatiaPyBridgeRunOnceCommand_H

#include "CATCommand.h"
#include "CATSysErrorDef.h"

#include <string>

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

    static HRESULT ExecuteBridgeJob(
        const std::string& iJobPath = "",
        const std::string& iTransport = "runonce_file",
        unsigned __int64 iQueueSequence = 0);

private:
    int _executed;
};

#endif
