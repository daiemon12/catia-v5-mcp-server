#include "CatiaPyBridgeJson.h"
#include "CatiaPyBridgeResponse.h"

#include <cctype>
#include <cstdlib>
#include <sstream>

static void SkipWhitespace(const std::string& text, size_t& pos)
{
    while (pos < text.size() && std::isspace(static_cast<unsigned char>(text[pos])))
        ++pos;
}

size_t CatiaPyBridgeJson::FindValueStart(
    const std::string& json,
    const std::string& key)
{
    const std::string token = "\"" + key + "\"";
    size_t pos = json.find(token);
    if (pos == std::string::npos)
        return std::string::npos;

    pos += token.size();
    SkipWhitespace(json, pos);
    if (pos >= json.size() || json[pos] != ':')
        return std::string::npos;

    ++pos;
    SkipWhitespace(json, pos);
    return pos;
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
    const std::string& json,
    const std::string& key,
    std::string& outValue)
{
    size_t pos = FindValueStart(json, key);
    if (pos == std::string::npos || pos >= json.size() || json[pos] != '"')
        return false;

    ++pos;
    std::ostringstream out;
    while (pos < json.size())
    {
        char ch = json[pos++];
        if (ch == '"')
        {
            outValue = out.str();
            return true;
        }

        if (ch == '\\' && pos < json.size())
        {
            char esc = json[pos++];
            switch (esc)
            {
            case '"':
                out << '"';
                break;
            case '\\':
                out << '\\';
                break;
            case '/':
                out << '/';
                break;
            case 'b':
                out << '\b';
                break;
            case 'f':
                out << '\f';
                break;
            case 'n':
                out << '\n';
                break;
            case 'r':
                out << '\r';
                break;
            case 't':
                out << '\t';
                break;
            case 'u':
                out << '?';
                if (pos + 4 <= json.size())
                    pos += 4;
                break;
            default:
                out << esc;
                break;
            }
        }
        else
        {
            out << ch;
        }
    }

    return false;
}

bool CatiaPyBridgeJson::GetObjectRaw(
    const std::string& json,
    const std::string& key,
    std::string& outJson)
{
    size_t pos = FindValueStart(json, key);
    if (pos == std::string::npos || pos >= json.size() || json[pos] != '{')
        return false;

    const size_t start = pos;
    int depth = 0;
    bool inString = false;
    bool escaped = false;

    while (pos < json.size())
    {
        const char ch = json[pos++];

        if (inString)
        {
            if (escaped)
            {
                escaped = false;
            }
            else if (ch == '\\')
            {
                escaped = true;
            }
            else if (ch == '"')
            {
                inString = false;
            }
            continue;
        }

        if (ch == '"')
        {
            inString = true;
        }
        else if (ch == '{')
        {
            ++depth;
        }
        else if (ch == '}')
        {
            --depth;
            if (depth == 0)
            {
                outJson = json.substr(start, pos - start);
                return true;
            }
        }
    }

    return false;
}

bool CatiaPyBridgeJson::GetObjectArrayRaw(
    const std::string& json,
    const std::string& key,
    std::vector<std::string>& outObjects)
{
    outObjects.clear();
    size_t pos = FindValueStart(json, key);
    if (pos == std::string::npos || pos >= json.size() || json[pos] != '[')
        return false;
    ++pos;

    while (pos < json.size())
    {
        while (pos < json.size() && std::isspace(static_cast<unsigned char>(json[pos])))
            ++pos;
        if (pos < json.size() && json[pos] == ']')
            return true;
        if (pos >= json.size() || json[pos] != '{')
            return false;

        const size_t start = pos;
        int depth = 0;
        bool inString = false;
        bool escaped = false;
        while (pos < json.size())
        {
            const char ch = json[pos++];
            if (inString)
            {
                if (escaped)
                    escaped = false;
                else if (ch == '\\')
                    escaped = true;
                else if (ch == '"')
                    inString = false;
                continue;
            }
            if (ch == '"')
                inString = true;
            else if (ch == '{')
                ++depth;
            else if (ch == '}' && --depth == 0)
            {
                outObjects.push_back(json.substr(start, pos - start));
                break;
            }
        }
        if (depth != 0)
            return false;
        while (pos < json.size() && std::isspace(static_cast<unsigned char>(json[pos])))
            ++pos;
        if (pos < json.size() && json[pos] == ',')
        {
            ++pos;
            continue;
        }
        if (pos < json.size() && json[pos] == ']')
            return true;
        return false;
    }
    return false;
}

bool CatiaPyBridgeJson::GetStringArray(
    const std::string& json,
    const std::string& key,
    std::vector<std::string>& outValues)
{
    outValues.clear();
    size_t pos = FindValueStart(json, key);
    if (pos == std::string::npos || pos >= json.size() || json[pos] != '[')
        return false;
    ++pos;

    while (pos < json.size())
    {
        SkipWhitespace(json, pos);
        if (pos < json.size() && json[pos] == ']')
            return true;
        if (pos >= json.size() || json[pos] != '"')
            return false;
        ++pos;

        std::ostringstream value;
        bool closed = false;
        while (pos < json.size())
        {
            const char ch = json[pos++];
            if (ch == '"')
            {
                closed = true;
                break;
            }
            if (ch != '\\')
            {
                value << ch;
                continue;
            }
            if (pos >= json.size())
                return false;
            const char esc = json[pos++];
            switch (esc)
            {
            case '"': value << '"'; break;
            case '\\': value << '\\'; break;
            case '/': value << '/'; break;
            case 'b': value << '\b'; break;
            case 'f': value << '\f'; break;
            case 'n': value << '\n'; break;
            case 'r': value << '\r'; break;
            case 't': value << '\t'; break;
            case 'u':
                if (pos + 4 > json.size())
                    return false;
                value << '?';
                pos += 4;
                break;
            default:
                return false;
            }
        }
        if (!closed)
            return false;
        outValues.push_back(value.str());

        SkipWhitespace(json, pos);
        if (pos < json.size() && json[pos] == ',')
        {
            ++pos;
            continue;
        }
        if (pos < json.size() && json[pos] == ']')
            return true;
        return false;
    }
    return false;
}

int CatiaPyBridgeJson::GetIntValue(
    const std::string& json,
    const std::string& key,
    int defaultValue)
{
    size_t pos = FindValueStart(json, key);
    if (pos == std::string::npos)
        return defaultValue;

    bool negative = false;
    if (pos < json.size() && json[pos] == '-')
    {
        negative = true;
        ++pos;
    }

    if (pos >= json.size() || !std::isdigit(static_cast<unsigned char>(json[pos])))
        return defaultValue;

    int value = 0;
    while (pos < json.size() && std::isdigit(static_cast<unsigned char>(json[pos])))
    {
        value = value * 10 + (json[pos] - '0');
        ++pos;
    }

    return negative ? -value : value;
}

double CatiaPyBridgeJson::GetDoubleValue(
    const std::string& json,
    const std::string& key,
    double defaultValue)
{
    size_t pos = FindValueStart(json, key);
    if (pos == std::string::npos)
        return defaultValue;

    char* endPtr = NULL;
    const double value = std::strtod(json.c_str() + pos, &endPtr);
    if (endPtr == json.c_str() + pos)
        return defaultValue;
    return value;
}

bool CatiaPyBridgeJson::GetBoolValue(
    const std::string& json,
    const std::string& key,
    bool defaultValue)
{
    size_t pos = FindValueStart(json, key);
    if (pos == std::string::npos)
        return defaultValue;

    if (json.compare(pos, 4, "true") == 0)
        return true;
    if (json.compare(pos, 5, "false") == 0)
        return false;
    return defaultValue;
}

bool CatiaPyBridgeJson::GetDoubleArray2(
    const std::string& json,
    const std::string& key,
    double& outX,
    double& outY)
{
    size_t pos = FindValueStart(json, key);
    if (pos == std::string::npos || pos >= json.size() || json[pos] != '[')
        return false;

    ++pos;
    SkipWhitespace(json, pos);

    char* endPtr = NULL;
    const double x = std::strtod(json.c_str() + pos, &endPtr);
    if (endPtr == json.c_str() + pos)
        return false;
    pos = static_cast<size_t>(endPtr - json.c_str());
    SkipWhitespace(json, pos);

    if (pos >= json.size() || json[pos] != ',')
        return false;
    ++pos;
    SkipWhitespace(json, pos);

    endPtr = NULL;
    const double y = std::strtod(json.c_str() + pos, &endPtr);
    if (endPtr == json.c_str() + pos)
        return false;
    pos = static_cast<size_t>(endPtr - json.c_str());
    SkipWhitespace(json, pos);

    if (pos >= json.size() || json[pos] != ']')
        return false;

    outX = x;
    outY = y;
    return true;
}

bool CatiaPyBridgeJson::GetDoubleArrayFlat(
    const std::string& json,
    const std::string& key,
    std::vector<double>& outValues)
{
    outValues.clear();
    size_t pos = FindValueStart(json, key);
    if (pos == std::string::npos || pos >= json.size() || json[pos] != '[')
        return false;

    int depth = 0;
    bool inString = false;
    bool escaped = false;
    bool sawArray = false;

    while (pos < json.size())
    {
        char ch = json[pos];

        if (inString)
        {
            if (escaped)
                escaped = false;
            else if (ch == '\\')
                escaped = true;
            else if (ch == '"')
                inString = false;
            ++pos;
            continue;
        }

        if (ch == '"')
        {
            inString = true;
            ++pos;
            continue;
        }

        if (ch == '[')
        {
            ++depth;
            sawArray = true;
            ++pos;
            continue;
        }

        if (ch == ']')
        {
            --depth;
            ++pos;
            if (sawArray && depth == 0)
                return !outValues.empty();
            if (depth < 0)
                return false;
            continue;
        }

        if (depth > 0 && (ch == '-' || ch == '+' || ch == '.' || std::isdigit(static_cast<unsigned char>(ch))))
        {
            char* endPtr = NULL;
            const double value = std::strtod(json.c_str() + pos, &endPtr);
            if (endPtr != json.c_str() + pos)
            {
                outValues.push_back(value);
                pos = static_cast<size_t>(endPtr - json.c_str());
                continue;
            }
        }

        ++pos;
    }

    outValues.clear();
    return false;
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
