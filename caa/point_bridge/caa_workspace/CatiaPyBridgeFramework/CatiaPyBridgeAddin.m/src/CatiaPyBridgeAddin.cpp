#include "CatiaPyBridgeAddin.h"
#include "CATCommandHeader.h"
#include "CATCreateWorkshop.h"
#include "CATIAfrGeneralWksAddin.h"
MacDeclareHeader(CatiaPyBridgeCommandHeader);
CATImplementClass(CatiaPyBridgeAddin, Implementation, CATBaseUnknown, CATNull);
#include "TIE_CATIAfrGeneralWksAddin.h"
TIE_CATIAfrGeneralWksAddin(CatiaPyBridgeAddin);
CatiaPyBridgeAddin::CatiaPyBridgeAddin() : CATBaseUnknown() {}
CatiaPyBridgeAddin::~CatiaPyBridgeAddin() {}
void CatiaPyBridgeAddin::CreateCommands()
{
    new CatiaPyBridgeCommandHeader("CatiaPyBridge_RunOnce", "CatiaPyBridgeCmdModule",
        "CatiaPyBridgeRunOnceCommand", (void*)NULL);
}
CATCmdContainer* CatiaPyBridgeAddin::CreateToolbars()
{
    NewAccess(CATCmdContainer, root, CatiaPyBridgePointRoot);
    return root;
}
