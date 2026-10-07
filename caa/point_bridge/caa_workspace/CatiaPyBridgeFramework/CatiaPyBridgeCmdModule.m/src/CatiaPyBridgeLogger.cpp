#include "CatiaPyBridgeLogger.h"

#include <cstdlib>
#include <ctime>
#include <fstream>
#include <sstream>
#include <windows.h>

std::string CatiaPyBridgeLogger::RootDir()
{
    const char* temp = std::getenv("TEMP");
    if (temp == NULL || temp[0] == '\0')
        temp = std::getenv("TMP");
    if (temp == NULL || temp[0] == '\0')
        return ".\\CatiaPyBridge";

    std::string root(temp);
    if (!root.empty() && root[root.size() - 1] != '\\' && root[root.size() - 1] != '/')
        root += "\\";
    root += "CatiaPyBridge";
    return root;
}

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
    const std::string root = RootDir();
    const std::string logs = root + "\\logs";
    CreateDirectoryA(root.c_str(), NULL);
    CreateDirectoryA(logs.c_str(), NULL);

    std::time_t now = std::time(NULL);
    std::tm* tmNow = std::localtime(&now);
    char timestamp[32] = {0};
    if (tmNow != NULL)
        std::strftime(timestamp, sizeof(timestamp), "%Y-%m-%dT%H:%M:%S", tmNow);

    std::ofstream out((logs + "\\CatiaPyBridge.log").c_str(), std::ios::out | std::ios::app);
    if (!out)
        return;

    out << timestamp << " " << level << " " << message << "\n";
}
