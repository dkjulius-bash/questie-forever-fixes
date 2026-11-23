local ADDON_NAME, ns = ...
local OWNER = "QuestieForeverFixes"
local PREFIX = "|cff33ff99QFF|r "
local DATATYPES = {
    { "Quest", "questKeys" }, { "Npc", "npcKeys" },
    { "Object", "objectKeys" }, { "Item", "itemKeys" },
}

local state = { status = "init", applied = {}, errors = {}, skippedFields = 0 }

local function say(text)
    local msg = PREFIX .. text
    if DEFAULT_CHAT_FRAME and DEFAULT_CHAT_FRAME.AddMessage then
        DEFAULT_CHAT_FRAME:AddMessage(msg)
    else
        print(msg)
    end
end

local function translate(src, keys)
    local rows, n = {}, 0
    for id, fields in pairs(src or {}) do
        local row = {}
        for name, value in pairs(fields) do
            local key = keys[name]
            if key then
                row[key] = value
            else
                state.skippedFields = state.skippedFields + 1
            end
        end
        rows[id] = row
        n = n + 1
    end
    return rows, n
end

local function apply()
    local lib = _G.LibQuestieDB
    if type(lib) ~= "table" or type(lib.RequireContract) ~= "function" then
        state.status = "no-lib"
        say("LibQuestieDB not found - fixes inactive")
        return
    end
    local ok, msg = lib.RequireContract(4)
    if not ok then
        state.status = "contract"
        say("LibQuestieDB contract check failed: " .. tostring(msg))
        return
    end
    if type(ns.data) ~= "function" then
        state.status = "no-data"
        say("no data (Data.lua missing or invalid) - fixes inactive")
        return
    end
    local raw = ns.data()
    local failed = {}
    for _, dt in ipairs(DATATYPES) do
        local name, keysName = dt[1], dt[2]
        local rows, n = translate(raw[name], lib.Enum[keysName])
        if n > 0 then
            lib.RegisterRuntimeCorrection(OWNER, name, "traces", function() return rows end, 10)
            local aok, err = pcall(lib.ApplyRegisteredCorrections, OWNER)
            if aok then
                state.applied[name] = n
            else
                state.errors[name] = tostring(err)
                failed[#failed + 1] = name
                pcall(lib.Corrections.UnregisterCorrection, OWNER, name, "traces")
                pcall(lib.ApplyRegisteredCorrections, OWNER)
            end
        end
    end
    raw = nil
    if #failed > 0 then
        state.status = "partial"
        say("failed to apply: " .. table.concat(failed, ", ") .. " (see /qff)")
    else
        state.status = "ok"
    end
end

local function addonVersion(addon)
    local get = (C_AddOns and C_AddOns.GetAddOnMetadata) or GetAddOnMetadata
    if not get then return "?" end
    local ok, v = pcall(get, addon, "Version")
    return (ok and v) or "?"
end

local function status()
    local lib = _G.LibQuestieDB
    local meta = ns.meta or {}
    local counts = meta.counts or {}
    local parts = {}
    for _, dt in ipairs(DATATYPES) do
        local name = dt[1]
        local a, g = state.applied[name] or 0, counts[name]
        parts[#parts + 1] = name .. " " .. a .. ((g and g ~= a) and ("/" .. g) or "")
    end
    say("status: " .. state.status .. " | patched " .. table.concat(parts, ", "))
    local cur, gen = addonVersion("QuestieDB"), meta.questieDBVersion
    local line = "contract " .. tostring(lib and lib.contractVersion or "?")
        .. " (min " .. tostring(lib and lib.minSupportedContract or "?") .. ")"
        .. " | QuestieDB " .. cur
    if gen and gen ~= cur then line = line .. " (data generated for " .. gen .. "; rerun refresh)" end
    line = line .. " | data " .. tostring(meta.generatedAt or "?") .. ", sessions " .. tostring(meta.sessions or "?")
        .. " | skipped fields " .. state.skippedFields
    say(line)
    for _, dt in ipairs(DATATYPES) do
        if state.errors[dt[1]] then say("error " .. dt[1] .. ": " .. state.errors[dt[1]]) end
    end
end

SLASH_QUESTIEFOREVERFIXES1 = "/qff"
SlashCmdList.QUESTIEFOREVERFIXES = function(msg)
    local ok, err = pcall(function()
        msg = string.lower((tostring(msg or ""):gsub("^%s+", ""):gsub("%s+$", "")))
        if msg == "" or msg == "status" then
            status()
        elseif msg == "off" then
            QuestieForeverFixesDB.disabled = true
            say("will be disabled after /reload")
        elseif msg == "on" then
            QuestieForeverFixesDB.disabled = nil
            say("will be enabled after /reload")
        else
            say("usage: /qff [status|on|off]")
        end
    end)
    if not ok then say("error: " .. tostring(err)) end
end

local frame = CreateFrame("Frame")
frame:RegisterEvent("ADDON_LOADED")
frame:SetScript("OnEvent", function(self, event, arg1)
    if arg1 ~= ADDON_NAME then return end
    self:UnregisterEvent("ADDON_LOADED")
    QuestieForeverFixesDB = type(QuestieForeverFixesDB) == "table" and QuestieForeverFixesDB or {}
    if QuestieForeverFixesDB.disabled then
        state.status = "disabled"
        say("disabled (/qff on, then /reload to enable)")
        return
    end
    local ok, err = pcall(apply)
    if not ok then
        state.status = "error"
        say("error: " .. tostring(err) .. " (see /qff)")
    end
end)
