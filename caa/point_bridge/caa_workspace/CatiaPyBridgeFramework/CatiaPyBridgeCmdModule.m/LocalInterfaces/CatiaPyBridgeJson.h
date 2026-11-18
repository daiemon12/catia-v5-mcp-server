#ifndef CatiaPyBridgeJson_H
#define CatiaPyBridgeJson_H

#include "nlohmann_json.h"
#include <string>

class CatiaPyBridgeResponse;

class CatiaPyBridgeJson
{
public:
    static bool ParseObject(const std::string& text, nlohmann::json& object);
    static std::string Escape(const std::string& value);
    static bool GetStringValue(
        const nlohmann::json& object, const char* key, std::string& value);
    static double GetDoubleValue(
        const nlohmann::json& object, const char* key, double defaultValue);
    static bool GetBoolValue(
        const nlohmann::json& object, const char* key, bool defaultValue);
    static std::string BuildResponseJson(const CatiaPyBridgeResponse& response);
};

#endif
