#ifndef CatiaPyBridgeJson_H
#define CatiaPyBridgeJson_H

#include <string>
#include <vector>

class CatiaPyBridgeResponse;

class CatiaPyBridgeJson
{
public:
    static std::string Escape(const std::string& value);
    static bool GetStringValue(
        const std::string& json,
        const std::string& key,
        std::string& outValue);
    static bool GetObjectRaw(
        const std::string& json,
        const std::string& key,
        std::string& outJson);
    static bool GetObjectArrayRaw(
        const std::string& json,
        const std::string& key,
        std::vector<std::string>& outObjects);
    static bool GetStringArray(
        const std::string& json,
        const std::string& key,
        std::vector<std::string>& outValues);
    static int GetIntValue(
        const std::string& json,
        const std::string& key,
        int defaultValue);
    static double GetDoubleValue(
        const std::string& json,
        const std::string& key,
        double defaultValue);
    static bool GetBoolValue(
        const std::string& json,
        const std::string& key,
        bool defaultValue);
    static bool GetDoubleArray2(
        const std::string& json,
        const std::string& key,
        double& outX,
        double& outY);
    static bool GetDoubleArrayFlat(
        const std::string& json,
        const std::string& key,
        std::vector<double>& outValues);
    static std::string BuildResponseJson(const CatiaPyBridgeResponse& response);

private:
    static size_t FindValueStart(
        const std::string& json,
        const std::string& key);
};

#endif
