local _, ns = ...
ns.meta = { generatedAt = "2026-11-23T12:00:00Z", questieDBVersion = "1.1.5", questieVersion = "12.12.0", sessions = 20, characters = 2, extractorCommit = "15c1191", counts = { Quest = 2, Npc = 2, Object = 1, Item = 1 } }
ns.data = function()
    return {
        Quest = {
            [95219] = { ["startedBy_add"] = { [1] = {257558} }, ["finishedBy_add"] = { [1] = {257559} }, ["objectives"] = { [1] = {{1234}} } },
            [95220] = { ["name"] = "Fixture Quest", ["questLevel"] = 60 },
        },
        Npc = {
            [257558] = { ["spawns"] = { [16591] = {{45.1, 60.2}} }, ["questStarts_add"] = {95219} },
            [257559] = { ["questEnds_add"] = {95219}, ["name"] = "Fixture NPC" },
        },
        Object = { [5001] = { ["spawns"] = { [1519] = {{10.5, 20.5}} }, ["questStarts_add"] = {95220} } },
        Item = { [5555] = { ["npcDrops_add"] = {1234} } },
    }
end
