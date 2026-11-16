-- fbp simulation harness (Factorio 2.x, base mod only).
-- Loaded as a scenario via `factorio --test-scenario`. Builds the blueprint on an
-- empty lab-tile surface, feeds the inputs / drains the outputs described in the
-- spec, samples machine status, and writes script-output/fbp-result.json.
local input = require("fbp_input")
local spec = helpers.json_to_table(input.spec_json)

local RESULT_FILE = "fbp-result.json"
local SAMPLE_EVERY = 30
local TRACKED_TYPES = {
  ["assembling-machine"] = true, ["furnace"] = true, ["rocket-silo"] = true,
  ["lab"] = true, ["mining-drill"] = true, ["boiler"] = true, ["generator"] = true,
  ["inserter"] = true, ["offshore-pump"] = true, ["reactor"] = true,
}
local STATUS_NAME = {}
for name, value in pairs(defines.entity_status) do STATUS_NAME[value] = name end

local S = nil -- runtime state (not persisted; a test run is never saved/loaded)

local function finish(result)
  helpers.write_file(RESULT_FILE, helpers.table_to_json(result), false)
  script.finish_test(result.ok == true)
end

local function fail(message, extra)
  local result = extra or {}
  result.ok = false
  result.error = message
  finish(result)
end

local function add_count(tbl, name, count)
  tbl[name] = (tbl[name] or 0) + count
end

-- Find the entity of one of `types` covering blueprint tile {x, y}.
local function entity_at(tile, types)
  local x, y = tile[1] + S.offset.x, tile[2] + S.offset.y
  local found = S.surface.find_entities_filtered{
    area = {{x + 0.1, y + 0.1}, {x + 0.9, y + 0.9}}, type = types,
  }
  return found[1]
end

local BELT_TYPES = {"transport-belt", "underground-belt", "splitter"}
local CHEST_TYPES = {"container", "logistic-container", "infinity-container"}
local FLUID_TYPES = {"pipe", "pipe-to-ground", "storage-tank", "infinity-pipe"}

local function resolve_io(list, what)
  local out = {}
  for i, io in ipairs(list or {}) do
    local types = (io.kind == "belt" and BELT_TYPES) or (io.kind == "chest" and CHEST_TYPES)
      or (io.kind == "fluid" and FLUID_TYPES)
    if not types then return nil, what .. " #" .. i .. ": unknown kind '" .. tostring(io.kind) .. "'" end
    local entity = entity_at(io.position, types)
    if not entity then
      return nil, string.format("%s #%d: no %s entity at blueprint tile (%s, %s)",
        what, i, io.kind, io.position[1], io.position[2])
    end
    out[i] = {io = io, entity = entity, collected = {}, inserted = {}, credit = {0, 0}}
  end
  return out
end

local function setup()
  local surface = game.create_surface("fbp")
  surface.generate_with_lab_tiles = true
  surface.always_day = true
  surface.request_to_generate_chunks({0, 0}, 8)
  surface.force_generate_chunk_requests()
  local force = game.forces.player
  if spec.research_all then
    force.research_all_technologies()
  else
    for _, recipe in pairs(force.recipes) do recipe.enabled = true end
  end

  local inventory = game.create_inventory(1)
  local stack = inventory[1]
  if stack.import_stack(input.blueprint) ~= 0 or not stack.is_blueprint then
    return fail("blueprint string could not be imported (must be a single blueprint, not a book)")
  end
  local bp_entities = stack.get_blueprint_entities() or {}
  if #bp_entities == 0 then return fail("blueprint has no entities") end

  local ghosts = stack.build_blueprint{
    surface = surface, force = force, position = {0, 0},
    build_mode = defines.build_mode.forced, skip_fog_of_war = false, raise_built = false,
  }

  -- world position = blueprint position + offset
  local bp_min, world_min = {x = math.huge, y = math.huge}, {x = math.huge, y = math.huge}
  for _, e in pairs(bp_entities) do
    bp_min.x = math.min(bp_min.x, e.position.x); bp_min.y = math.min(bp_min.y, e.position.y)
  end
  local ghost_count = 0
  for _, g in pairs(ghosts) do
    if g.valid and g.type == "entity-ghost" then
      ghost_count = ghost_count + 1
      world_min.x = math.min(world_min.x, g.position.x); world_min.y = math.min(world_min.y, g.position.y)
    end
  end
  local offset = {x = world_min.x - bp_min.x, y = world_min.y - bp_min.y}

  local problems = {}
  if ghost_count ~= #bp_entities then
    problems[#problems + 1] = string.format(
      "only %d of %d blueprint entities could be placed", ghost_count, #bp_entities)
  end

  local tracked = {}
  local burners = {}
  for _, ghost in pairs(ghosts) do
    if ghost.valid and ghost.type == "entity-ghost" then
      local name, pos = ghost.ghost_name, ghost.position
      local requests = ghost.item_requests
      local _, entity, proxy = ghost.revive{raise_revive = false}
      if not entity then
        problems[#problems + 1] = string.format("could not build %s at (%s, %s)",
          name, pos.x - offset.x, pos.y - offset.y)
      else
        if proxy and proxy.valid then proxy.destroy() end
        local modules = entity.get_module_inventory()
        if modules and requests then
          for _, req in pairs(requests) do
            modules.insert{name = req.name, count = req.count, quality = req.quality}
          end
        end
        if entity.burner then burners[#burners + 1] = entity end
        if TRACKED_TYPES[entity.type] then
          tracked[#tracked + 1] = {entity = entity, status = {}}
        end
      end
    end
  end
  inventory.destroy()

  S = {surface = surface, force = force, offset = offset, tracked = tracked, burners = burners,
       problems = problems, samples = 0, start_tick = game.tick}

  -- Power: one electric-energy-interface per electric network, wired by script.
  local bbox_max_x = -math.huge
  for _, e in pairs(surface.find_entities()) do bbox_max_x = math.max(bbox_max_x, e.position.x) end
  local seen, n = {}, 0
  for _, pole in pairs(surface.find_entities_filtered{type = "electric-pole"}) do
    local id = pole.electric_network_id
    if id and not seen[id] then
      seen[id] = true
      local at = {bbox_max_x + 20, pole.position.y + n * 6}
      n = n + 1
      local source = surface.create_entity{name = "electric-energy-interface", position = at, force = force}
      source.electric_buffer_size = 1e12
      source.power_production = 1e12
      source.power_usage = 0
      source.energy = 1e12
      local helper = surface.create_entity{name = "small-electric-pole", position = {at[1], at[2] + 3}, force = force}
      helper.get_wire_connector(defines.wire_connector_id.pole_copper, true).connect_to(
        pole.get_wire_connector(defines.wire_connector_id.pole_copper, true), false, defines.wire_origin.script)
    end
  end
  S.network_count = n

  local err
  S.inputs, err = resolve_io(spec.inputs, "input")
  if not S.inputs then return fail(err, {problems = problems}) end
  S.outputs, err = resolve_io(spec.outputs, "output")
  if not S.outputs then return fail(err, {problems = problems}) end
end

local function feed_belt(io)
  local items = {io.io.left or io.io.item, io.io.right or io.io.item}
  for lane = 1, 2 do
    local item = items[lane]
    if item then
      -- optional rate limit (items/min per lane); default is a fully compressed lane
      local allowed = true
      if io.io.per_minute then
        io.credit[lane] = math.min(io.credit[lane] + io.io.per_minute / 3600 / ((io.io.left or io.io.right) and 1 or 2), 4)
        allowed = io.credit[lane] >= 1
      end
      local line = io.entity.get_transport_line(lane)
      if allowed and line.can_insert_at_back() and line.insert_at_back({name = item, count = 1}) then
        add_count(io.inserted, item, 1)
        if io.io.per_minute then io.credit[lane] = io.credit[lane] - 1 end
      end
    end
  end
end

local function drain_belt(io, counting)
  for lane = 1, io.entity.get_max_transport_line_index() do
    local line = io.entity.get_transport_line(lane)
    if #line > 0 then
      if counting then
        for _, item in pairs(line.get_contents()) do add_count(io.collected, item.name, item.count) end
      end
      line.clear()
    end
  end
end

local function feed_chest(io)
  local inv = io.entity.get_inventory(defines.inventory.chest)
  local have = inv.get_item_count(io.io.item)
  local want = prototypes.item[io.io.item].stack_size * 2
  if have < want then
    add_count(io.inserted, io.io.item, inv.insert{name = io.io.item, count = want - have})
  end
end

local function drain_chest(io, counting)
  local inv = io.entity.get_inventory(defines.inventory.chest)
  if counting then
    for _, item in pairs(inv.get_contents()) do add_count(io.collected, item.name, item.count) end
  end
  inv.clear()
end

local function feed_fluid(io)
  local amount = io.entity.insert_fluid{name = io.io.fluid or io.io.item, amount = 1e6,
    temperature = io.io.temperature}
  add_count(io.inserted, io.io.fluid or io.io.item, amount)
end

local function drain_fluid(io, counting)
  for name, amount in pairs(io.entity.get_fluid_contents()) do
    local removed = io.entity.remove_fluid{name = name, amount = amount}
    if counting then add_count(io.collected, name, removed) end
  end
end

local function refuel()
  if not spec.fuel then return end
  for _, entity in pairs(S.burners) do
    if entity.valid then
      local inv = entity.get_fuel_inventory()
      if inv and inv.get_item_count(spec.fuel) < 5 then inv.insert{name = spec.fuel, count = 5} end
    end
  end
end

local function stats_snapshot()
  local items = S.force.get_item_production_statistics(S.surface)
  local fluids = S.force.get_fluid_production_statistics(S.surface)
  local snap = {produced = {}, consumed = {}}
  for _, stats in pairs{items, fluids} do
    for name, count in pairs(stats.input_counts) do snap.produced[name] = count end
    for name, count in pairs(stats.output_counts) do snap.consumed[name] = count end
  end
  return snap
end

local function diff(after, before)
  local out = {}
  for name, count in pairs(after) do
    local d = count - (before[name] or 0)
    if d > 0 then out[name] = d end
  end
  return out
end

local function sample()
  S.samples = S.samples + 1
  for _, t in pairs(S.tracked) do
    if t.entity.valid then
      local status = STATUS_NAME[t.entity.status] or "unknown"
      t.status[status] = (t.status[status] or 0) + 1
    end
  end
end

local function report()
  local after = stats_snapshot()
  local entities = {}
  for _, t in pairs(S.tracked) do
    local e = t.entity
    if e.valid then
      local recipe = nil
      if e.type == "assembling-machine" or e.type == "furnace" or e.type == "rocket-silo" then
        local r = e.get_recipe() or (e.type == "furnace" and e.previous_recipe and e.previous_recipe.name)
        recipe = r and (type(r) == "table" and r.name or r.name) or nil
      end
      entities[#entities + 1] = {
        name = e.name, type = e.type, recipe = recipe,
        position = {e.position.x - S.offset.x, e.position.y - S.offset.y},
        status = t.status,
        products_finished = (e.type ~= "inserter" and e.type ~= "boiler" and e.type ~= "generator"
          and e.type ~= "offshore-pump" and e.type ~= "reactor" and e.type ~= "mining-drill")
          and e.products_finished or nil,
      }
    end
  end
  local function io_report(list, key)
    local out = {}
    for i, io in ipairs(list) do
      out[i] = {kind = io.io.kind, position = io.io.position, items = io[key], entity = io.entity.name}
    end
    return out
  end
  finish{
    ok = true,
    problems = S.problems,
    offset = {S.offset.x, S.offset.y},
    warmup_ticks = spec.warmup_ticks, measure_ticks = spec.measure_ticks,
    samples = S.samples, electric_networks = S.network_count,
    produced = diff(after.produced, S.before.produced),
    consumed = diff(after.consumed, S.before.consumed),
    inputs = io_report(S.inputs, "inserted"),
    outputs = io_report(S.outputs, "collected"),
    entities = entities,
  }
end

script.on_event(defines.events.on_tick, function()
  if not S then
    local ok, err = pcall(setup)
    if not ok then return fail("harness error during setup: " .. tostring(err)) end
    if not S or not S.inputs or not S.outputs then return end
    return
  end
  local t = game.tick - S.start_tick
  local measuring = t > spec.warmup_ticks
  local ok, err = pcall(function()
    if t == spec.warmup_ticks then
      S.before = stats_snapshot()
      for _, io in pairs(S.inputs) do io.inserted = {} end
    end
    for _, io in pairs(S.inputs) do
      if io.io.kind == "belt" then feed_belt(io)
      elseif io.io.kind == "chest" then if t % 30 == 0 then feed_chest(io) end
      else feed_fluid(io) end
    end
    for _, io in pairs(S.outputs) do
      if io.io.kind == "belt" then drain_belt(io, measuring)
      elseif io.io.kind == "chest" then if t % 30 == 0 or t == spec.warmup_ticks then drain_chest(io, measuring) end
      else drain_fluid(io, measuring) end
    end
    if t % 60 == 0 then refuel() end
    if measuring and t % SAMPLE_EVERY == 0 then sample() end
    if t >= spec.warmup_ticks + spec.measure_ticks then
      for _, io in pairs(S.outputs) do
        if io.io.kind == "chest" then drain_chest(io, true) end
      end
      report()
    end
  end)
  if not ok then fail("harness error at tick " .. t .. ": " .. tostring(err)) end
end)
