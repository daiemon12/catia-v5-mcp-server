#include "CatiaPyBridgeJson.h"
#include "CatiaPyBridgeResponse.h"

#include <sstream>

bool CatiaPyBridgeJson::ParseObject(const std::string& text, nlohmann::json& object)
{
    object = nlohmann::json::parse(text, nullptr, false);
    return object.is_object();
}

std::string CatiaPyBridgeJson::Escape(const std::string& value)
{
    std::ostringstream out;
    for (size_t i = 0; i < value.size(); ++i)
    {
        const unsigned char ch = static_cast<unsigned char>(value[i]);
        switch (ch)
        {
        case '"':
            out << "\\\"";
            break;
        case '\\':
            out << "\\\\";
            break;
        case '\b':
            out << "\\b";
            break;
        case '\f':
            out << "\\f";
            break;
        case '\n':
            out << "\\n";
            break;
        case '\r':
            out << "\\r";
            break;
        case '\t':
            out << "\\t";
            break;
        default:
            if (ch < 0x20)
            {
                const char* hex = "0123456789abcdef";
                out << "\\u00" << hex[(ch >> 4) & 0x0f] << hex[ch & 0x0f];
            }
            else
            {
                out << value[i];
            }
            break;
        }
    }
    return out.str();
}

bool CatiaPyBridgeJson::GetStringValue(
    const nlohmann::json& object, const char* key, std::string& value)
{
    const auto field = object.find(key);
    if (field == object.end() || !field->is_string())
        return false;
    value = field->get<std::string>();
    return true;
}

double CatiaPyBridgeJson::GetDoubleValue(
    const nlohmann::json& object, const char* key, double defaultValue)
{
    const auto field = object.find(key);
    return field != object.end() && field->is_number() ? field->get<double>() : defaultValue;
}

bool CatiaPyBridgeJson::GetBoolValue(
    const nlohmann::json& object, const char* key, bool defaultValue)
{
    const auto field = object.find(key);
    return field != object.end() && field->is_boolean() ? field->get<bool>() : defaultValue;
}

std::string CatiaPyBridgeJson::BuildResponseJson(const CatiaPyBridgeResponse& response)
{
    std::ostringstream out;
    out << "{\n";
    out << "  \"id\": \"" << Escape(response.JobId) << "\",\n";
    out << "  \"ok\": " << (response.Ok ? "true" : "false") << ",\n";
    out << "  \"method\": \"" << Escape(response.Method) << "\",\n";

    if (response.Ok)
    {
        out << "  \"result\": " << (response.ResultJson.empty() ? "{}" : response.ResultJson) << ",\n";
    }
    else
    {
        out << "  \"error\": {\n";
        out << "    \"code\": \"" << Escape(response.ErrorCode) << "\",\n";
        out << "    \"message\": \"" << Escape(response.ErrorMessage) << "\"";
        if (!response.ErrorDetail.empty())
            out << ",\n    \"detail\": \"" << Escape(response.ErrorDetail) << "\"\n";
        else
            out << "\n";
        out << "  },\n";
    }

    out << "  \"meta\": {\n";
    out << "    \"elapsed_ms\": " << response.ElapsedMs << ",\n";
    out << "    \"command\": \"CatiaPyBridge_RunOnce\",\n";
    out << "    \"transport\": \"" << Escape(response.Transport) << "\"";
    if (response.QueueSequence > 0)
        out << ",\n    \"queue_sequence\": " << response.QueueSequence << "\n";
    else
        out << "\n";
    out << "  }\n";
    out << "}\n";
    return out.str();
}
