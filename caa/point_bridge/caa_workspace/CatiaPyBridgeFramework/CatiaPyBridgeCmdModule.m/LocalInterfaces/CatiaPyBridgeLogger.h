#ifndef CatiaPyBridgeLogger_H
#define CatiaPyBridgeLogger_H

#include <string>

class CatiaPyBridgeLogger
{
public:
    static void Info(const std::string& message);
    static void Error(const std::string& message);

private:
    static void Write(const std::string& level, const std::string& message);
    static std::string RootDir();
};

#endif
