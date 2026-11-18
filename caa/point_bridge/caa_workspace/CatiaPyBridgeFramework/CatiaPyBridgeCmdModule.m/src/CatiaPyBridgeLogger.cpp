#include "CatiaPyBridgeLogger.h"
#include "CatiaPyBridgeFileBridge.h"

#include <ctime>
#include <fstream>

void CatiaPyBridgeLogger::Info(const std::string& message)
{
    Write("INFO", message);
}

void CatiaPyBridgeLogger::Error(const std::string& message)
{
    Write("ERROR", message);
}

void CatiaPyBridgeLogger::Write(const std::string& level, const std::string& message)
{
    const std::wstring root = CatiaPyBridgeFileBridge::RootDirectory();
    if (root.empty())
        return;

    std::time_t now = std::time(NULL);
    std::tm* tmNow = std::localtime(&now);
    char timestamp[32] = {0};
    if (tmNow != NULL)
        std::strftime(timestamp, sizeof(timestamp), "%Y-%m-%dT%H:%M:%S", tmNow);

    std::ofstream out((root + L"\\logs\\CatiaPyBridge.log").c_str(), std::ios::out | std::ios::app);
    if (!out)
        return;

    out << timestamp << " " << level << " " << message << "\n";
}
