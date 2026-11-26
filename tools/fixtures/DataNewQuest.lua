-- Fixture for verify_lua scenario k: new quests plus a class override on an existing quest.
local _, ns = ...
ns.meta = { generatedAt = "2026-01-01T00:00:00Z", questieDBVersion = "1.1.5", questieVersion = "0", sessions = 0, characters = 0, extractorCommit = "fixture",
    counts = { Quest = 3, Npc = 0, Object = 0, Item = 0 }, sources = { ["wh-page"] = 2, ["class-map"] = 1 } }
ns.data = function()
    return {
        Quest = {
            [84197] = { name = "Saving the Best for Last", questLevel = 60, requiredLevel = 58, startedBy = { [1] = { 230319 } },
                finishedBy = { [1] = { 230319 } }, requiredRaces = 4294967373, requiredClasses = 128,
                objectivesText = { "Give Deliana your Magister's Crown and Magister's Robes." },
                objectives = { [3] = { { 16686 }, { 16688 } } }, zoneOrSort = 1537 }, -- src: wh-page
            [82081] = { name = "Fixture Item Quest", questLevel = 60, requiredLevel = 58, startedBy = { [3] = { 221346 } },
                finishedBy = { [1] = { 14875 } }, sourceItemId = 221346 }, -- src: wh-page
            [84195] = { requiredClasses = 1024 }, -- src: class-map
        },
        Npc = {}, Object = {}, Item = {},
    }
end
