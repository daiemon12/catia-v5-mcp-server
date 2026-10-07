#ifndef CatiaPyBridgeAddin_H
#define CatiaPyBridgeAddin_H

#include "CATBaseUnknown.h"

class CATCmdContainer;

class CatiaPyBridgeAddin : public CATBaseUnknown
{
    CATDeclareClass;

public:
    CatiaPyBridgeAddin();
    virtual ~CatiaPyBridgeAddin();

    void CreateCommands();
    CATCmdContainer* CreateToolbars();

private:
    CatiaPyBridgeAddin(CatiaPyBridgeAddin&);
    CatiaPyBridgeAddin& operator=(CatiaPyBridgeAddin&);
};

#endif
