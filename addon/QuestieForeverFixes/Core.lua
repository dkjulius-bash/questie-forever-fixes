local ADDON_NAME, ns = ...
local OWNER = "QuestieForeverFixes"
local PREFIX = "|cff33ff99QFF|r "
local DATATYPES = {
    { "Quest", "questKeys" }, { "Npc", "npcKeys" },
    { "Object", "objectKeys" }, { "Item", "itemKeys" },
}

local LOCAL_GLOBAL = "QuestieForeverFixes_LocalData"
local DEDUPE_DIST = 0.5 -- map units

local state = { status = "init", applied = {}, errors = {}, skippedFields = 0, expected = {}, localStatus = "none" }

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

local function copyList(t)
    local r = {}
    for i, v in ipairs(t) do r[i] = v end
    return r
end

local function isPoint(p)
    return type(p) == "table" and type(p[1]) == "number" and type(p[2]) == "number"
end

local function mergeSpawns(sh, lo)
    local res = {}
    for z, pts in pairs(sh) do
        res[z] = type(pts) == "table" and copyList(pts) or pts
    end
    local lim = DEDUPE_DIST * DEDUPE_DIST
    for z, pts in pairs(lo) do
        if type(pts) == "table" then
            local cur = res[z]
            if type(cur) ~= "table" then
                res[z] = copyList(pts)
            else
                for _, p in ipairs(pts) do
                    if isPoint(p) then
                        local far = true
                        for _, q in ipairs(cur) do
                            if isPoint(q) then
                                local dx, dy = p[1] - q[1], p[2] - q[2]
                                if dx * dx + dy * dy <= lim then far = false; break end
                            end
                        end
                        if far then cur[#cur + 1] = p end
                    end
                end
            end
        end
    end
    return res
end

local function unionFlat(a, b)
    local res, seen = {}, {}
    for _, v in ipairs(a) do res[#res + 1] = v; seen[v] = true end
    for _, v in ipairs(b) do
        if not seen[v] then res[#res + 1] = v; seen[v] = true end
    end
    return res
end

local function mergeAdd(sv, lv)
    if type(sv[1]) == "number" or type(lv[1]) == "number" then
        return unionFlat(sv, lv)
    end
    local res = {}
    for g, gv in pairs(sv) do
        if type(gv) == "table" and type(lv[g]) == "table" then
            res[g] = unionFlat(gv, lv[g])
        elseif type(gv) == "table" then
            res[g] = copyList(gv)
        else
            res[g] = gv
        end
    end
    for g, gv in pairs(lv) do
        if res[g] == nil then
            res[g] = type(gv) == "table" and copyList(gv) or gv
        end
    end
    return res
end

local function countRows(t)
    local n = 0
    for _ in pairs(t) do n = n + 1 end
    return n
end

local function mergeData(shipped, loc)
    local merged, stats = {}, {}
    for _, dt in ipairs(DATATYPES) do
        local kind = dt[1]
        local sk = type(shipped[kind]) == "table" and shipped[kind] or {}
        local lk = type(loc[kind]) == "table" and loc[kind] or {}
        local out = {}
        for id, row in pairs(sk) do out[id] = row end
        local nNew, nMerged = 0, 0
        for id, lrow in pairs(lk) do
            local srow = sk[id]
            if srow == nil then
                out[id] = lrow
                nNew = nNew + 1
            elseif type(srow) == "table" and type(lrow) == "table" then
                local row = {}
                for f, v in pairs(srow) do row[f] = v end
                for f, lv in pairs(lrow) do
                    local sv = srow[f]
                    if sv == nil then
                        row[f] = lv
                    elseif f == "spawns" and type(sv) == "table" and type(lv) == "table" then
                        row[f] = mergeSpawns(sv, lv)
                    elseif string.sub(f, -4) == "_add" and type(sv) == "table" and type(lv) == "table" then
                        row[f] = mergeAdd(sv, lv)
                    end
                end
                out[id] = row
                nMerged = nMerged + 1
            end
        end
        merged[kind] = out
        stats[kind] = { shipped = countRows(sk), loc = countRows(lk), new = nNew, merged = nMerged, total = countRows(out) }
    end
    return merged, stats
end
ns.mergeData = mergeData

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
    local loc, localRaw, localMsg = _G[LOCAL_GLOBAL], nil, nil
    if loc ~= nil then
        if type(loc) == "table" and type(loc.data) == "function" then
            local lok, res = pcall(loc.data)
            if lok and type(res) == "table" then
                localRaw = res
                state.localMeta = type(loc.meta) == "table" and loc.meta or {}
            else
                localMsg = lok and "data() did not return a table" or tostring(res)
            end
        else
            localMsg = "invalid " .. LOCAL_GLOBAL
        end
        _G[LOCAL_GLOBAL] = nil
    end
    if localRaw then
        local mok, m, st = pcall(mergeData, raw, localRaw)
        if mok then
            raw = m
            state.mergeStats = st
            state.localStatus = "ok"
        else
            localMsg = tostring(m)
        end
    end
    if localMsg then
        state.localStatus = "error"
        state.localError = localMsg
        say("local fixes ignored: " .. localMsg .. " (see /qff)")
    end
    local failed = {}
    for _, dt in ipairs(DATATYPES) do
        local name, keysName = dt[1], dt[2]
        local rows, n = translate(raw[name], lib.Enum[keysName])
        state.expected[name] = n
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
        local a, g = state.applied[name] or 0, state.expected[name] or counts[name]
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
    local shippedParts = {}
    for _, dt in ipairs(DATATYPES) do
        shippedParts[#shippedParts + 1] = dt[1] .. " " .. tostring(counts[dt[1]] or 0)
    end
    local localPart
    if state.localStatus == "error" then
        localPart = "error: " .. tostring(state.localError)
    elseif state.localStatus == "ok" then
        local kinds = {}
        for _, dt in ipairs(DATATYPES) do
            local st = state.mergeStats and state.mergeStats[dt[1]]
            if st and st.loc > 0 then
                kinds[#kinds + 1] = dt[1] .. " " .. st.loc .. " (" .. st.new .. " new)"
            end
        end
        local lm = state.localMeta or {}
        localPart = (#kinds > 0 and table.concat(kinds, ", ") or "0 rows")
            .. " | built " .. tostring(lm.generatedAt or "?") .. ", sessions " .. tostring(lm.sessions or "?")
        if lm.questieDBVersion and cur ~= "?" and lm.questieDBVersion ~= cur then
            localPart = localPart .. " (built for QuestieDB " .. lm.questieDBVersion .. "; rebuild)"
        end
        if lm.shippedGeneratedAt and meta.generatedAt and lm.shippedGeneratedAt ~= meta.generatedAt then
            localPart = localPart .. " (shipped fixes changed since; rebuild)"
        end
    else
        localPart = "none"
    end
    say("shipped " .. table.concat(shippedParts, ", ") .. " | local " .. localPart)
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
