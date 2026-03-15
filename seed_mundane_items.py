"""
seed_mundane_items.py
Populates the mundane_items table with all standard D&D 5e PHB equipment.
Safe to re-run — uses upsert.

Store type keys (comma-separated in store_types field):
  general      General store / trading post (common consumables, basics)
  blacksmith   Metalsmith (metal weapons, heavy armor, metal tools)
  armorer      Armor specialist (all armor, shields)
  weaponsmith  Weapon specialist (all weapons)
  fletcher     Archery / fletching (bows, crossbows, ammo, nets)
  outfitter    Adventuring outfitter (packs, rope, lanterns, climbing gear)
  alchemist    Alchemist / herbalist (potions, acids, antitoxin, fire)
  scribe       Scribe / bookseller (books, paper, ink, spellbooks)
  clothier     Clothier / tailor (clothing, textiles)
  stable       Stable / animal trader (mounts, beasts, tack, land vehicles)
  shipwright   Shipwright / dock (waterborne vehicles)
  market       Trade goods market (raw commodities)
  instrument   Instrument shop (musical instruments)
  jeweler      Jeweler (gems, signet rings)
  exotic       Exotic dealer (rare animals, elephant, etc.)
"""

from db_manager import init_db, upsert_mundane_item, count_mundane_items

# ── helper ─────────────────────────────────────────────────────────────────────
def i(name, cat, sub, stores, cost_gp, wt=0,
      dmg="", dmg_type="", props="", ac="",
      str_req=0, stealth=False, cap="", spd="", desc=""):
    return {
        "name": name, "category": cat, "subcategory": sub,
        "store_types": stores, "cost_gp": cost_gp, "weight_lb": wt,
        "damage": dmg, "damage_type": dmg_type, "properties": props,
        "armor_class": ac, "str_requirement": str_req,
        "stealth_disadv": stealth, "capacity": cap, "speed": spd,
        "description": desc,
    }

AR = "Armor"
WP = "Weapon"
GR = "Adventuring Gear"
PK = "Equipment Pack"
TL = "Tool"
MT = "Mount/Animal"
VH = "Vehicle"
TG = "Trade Good"

ITEMS = [

    # ══════════════════════════════════════════════════════════════════════════
    # ARMOR
    # ══════════════════════════════════════════════════════════════════════════

    # Light
    i("Padded Armor",       AR,"Light Armor","armorer,blacksmith",     5,   8,  ac="11 + DEX mod",  stealth=True,
      desc="Quilted layers of cloth and batting. Inexpensive but noisy."),
    i("Leather Armor",      AR,"Light Armor","armorer,general,outfitter",10,10,  ac="11 + DEX mod",
      desc="Breastplate and shoulder protectors of stiffened leather. Popular adventuring choice."),
    i("Studded Leather",    AR,"Light Armor","armorer,blacksmith",     45,  13,  ac="12 + DEX mod",
      desc="Leather reinforced with close-set rivets or spikes. Better protection without sacrificing mobility."),

    # Medium
    i("Hide Armor",         AR,"Medium Armor","armorer,stable",        10,  12,  ac="12 + DEX mod (max 2)",
      desc="Crude armor from thick furs and animal hides. Common among barbarian tribes and druids."),
    i("Chain Shirt",        AR,"Medium Armor","armorer,blacksmith",    50,  20,  ac="13 + DEX mod (max 2)",
      desc="Made of interlocking metal rings, usually worn between layers of clothing."),
    i("Scale Mail",         AR,"Medium Armor","armorer,blacksmith",    50,  45,  ac="14 + DEX mod (max 2)", stealth=True,
      desc="Coat and leggings of leather covered with overlapping pieces of metal, like fish scales."),
    i("Breastplate",        AR,"Medium Armor","armorer,blacksmith",   400,  20,  ac="14 + DEX mod (max 2)",
      desc="Fitted metal chest plate with flexible leather for the rest. Expensive but light for its protection."),
    i("Half Plate",         AR,"Medium Armor","armorer,blacksmith",   750,  40,  ac="15 + DEX mod (max 2)", stealth=True,
      desc="Shaped metal plates covering most of the body. Leaves legs with just quilted padding."),

    # Heavy
    i("Ring Mail",          AR,"Heavy Armor","armorer,blacksmith",     30,  40,  ac="14", stealth=True,
      desc="Leather with heavy rings sewn into it. Inferior to chain mail; worn only by those who can't afford better."),
    i("Chain Mail",         AR,"Heavy Armor","armorer,blacksmith",     75,  55,  ac="16", str_req=13, stealth=True,
      desc="Interlocking metal rings with a layer of quilted fabric underneath. Standard knight armor."),
    i("Splint Armor",       AR,"Heavy Armor","armorer,blacksmith",    200,  60,  ac="17", str_req=15, stealth=True,
      desc="Narrow vertical strips of metal riveted to a backing of leather worn over chain mail."),
    i("Plate Armor",        AR,"Heavy Armor","armorer,blacksmith",   1500,  65,  ac="18", str_req=15, stealth=True,
      desc="Interlocking shaped metal plates covering the entire body with padding beneath. The pinnacle of protection."),

    # Shield
    i("Shield",             AR,"Shield","armorer,blacksmith,general",  10,   6,  ac="+2",
      desc="Made from wood or metal. Wielded in one hand. Cannot benefit from two shields simultaneously."),

    # ══════════════════════════════════════════════════════════════════════════
    # WEAPONS — Simple Melee
    # ══════════════════════════════════════════════════════════════════════════

    i("Club",               WP,"Simple Melee","general,blacksmith,weaponsmith", 0.1, 2,
      dmg="1d4", dmg_type="bludgeoning", props="Light",
      desc="A simple wooden cudgel. Found everywhere from peasant farms to city guards."),
    i("Dagger",             WP,"Simple Melee","general,blacksmith,weaponsmith", 2,   1,
      dmg="1d4", dmg_type="piercing", props="Finesse, Light, Thrown (20/60 ft)",
      desc="A short blade balanced for both hand-to-hand combat and throwing."),
    i("Greatclub",          WP,"Simple Melee","general,blacksmith,weaponsmith", 0.2, 10,
      dmg="1d8", dmg_type="bludgeoning", props="Two-handed",
      desc="A large, unwieldy club often fashioned from a thick tree branch."),
    i("Handaxe",            WP,"Simple Melee","blacksmith,weaponsmith,general", 5,   2,
      dmg="1d6", dmg_type="slashing", props="Light, Thrown (20/60 ft)",
      desc="A one-handed axe balanced for throwing. Standard issue for many soldiers."),
    i("Javelin",            WP,"Simple Melee","blacksmith,weaponsmith,outfitter",0.5, 2,
      dmg="1d6", dmg_type="piercing", props="Thrown (30/120 ft)",
      desc="A light spear designed for throwing. Devastating in massed volleys."),
    i("Light Hammer",       WP,"Simple Melee","blacksmith,weaponsmith",          2,   2,
      dmg="1d4", dmg_type="bludgeoning", props="Light, Thrown (20/60 ft)",
      desc="A small hammer balanced for throwing. Favored by clerics of forge gods."),
    i("Mace",               WP,"Simple Melee","blacksmith,weaponsmith",          5,   4,
      dmg="1d6", dmg_type="bludgeoning", props="—",
      desc="A metal-headed weapon effective against armored foes."),
    i("Quarterstaff",       WP,"Simple Melee","general,outfitter,weaponsmith",   0.2, 4,
      dmg="1d6", dmg_type="bludgeoning", props="Versatile (1d8)",
      desc="A sturdy wooden staff. Can be used one- or two-handed. Monks' and druids' weapon of choice."),
    i("Sickle",             WP,"Simple Melee","general,blacksmith",               1,   2,
      dmg="1d4", dmg_type="slashing", props="Light",
      desc="A curved farming blade repurposed as a weapon. Common in rural areas."),
    i("Spear",              WP,"Simple Melee","blacksmith,weaponsmith,general",   1,   3,
      dmg="1d6", dmg_type="piercing", props="Thrown (20/60 ft), Versatile (1d8)",
      desc="A pole with a pointed metal tip. One of the oldest and most common weapons."),

    # ══════════════════════════════════════════════════════════════════════════
    # WEAPONS — Simple Ranged
    # ══════════════════════════════════════════════════════════════════════════

    i("Light Crossbow",     WP,"Simple Ranged","fletcher,weaponsmith,blacksmith", 25,  5,
      dmg="1d8", dmg_type="piercing", props="Ammunition (80/320 ft), Loading, Two-handed",
      desc="A simple mechanical bow. Requires little training to use effectively."),
    i("Dart",               WP,"Simple Ranged","general,fletcher,weaponsmith",    0.05, 0.25,
      dmg="1d4", dmg_type="piercing", props="Finesse, Thrown (20/60 ft)",
      desc="A small weighted throwing spike. Easy to conceal."),
    i("Shortbow",           WP,"Simple Ranged","fletcher,weaponsmith",            25,   2,
      dmg="1d6", dmg_type="piercing", props="Ammunition (80/320 ft), Two-handed",
      desc="A shorter bow easily used from horseback or in tight spaces."),
    i("Sling",              WP,"Simple Ranged","general,fletcher",                0.1,  0,
      dmg="1d4", dmg_type="bludgeoning", props="Ammunition (30/120 ft)",
      desc="A leather strap used to hurl sling bullets or stones. Nearly free to use once you have one."),

    # ══════════════════════════════════════════════════════════════════════════
    # WEAPONS — Martial Melee
    # ══════════════════════════════════════════════════════════════════════════

    i("Battleaxe",          WP,"Martial Melee","blacksmith,weaponsmith",          10,  4,
      dmg="1d8", dmg_type="slashing", props="Versatile (1d10)",
      desc="A single- or double-headed axe, the standard weapon of dwarven warriors."),
    i("Flail",              WP,"Martial Melee","blacksmith,weaponsmith",          10,  2,
      dmg="1d8", dmg_type="bludgeoning", props="—",
      desc="A spiked metal ball on a chain. Can strike around shields."),
    i("Glaive",             WP,"Martial Melee","blacksmith,weaponsmith",          20,  6,
      dmg="1d10", dmg_type="slashing", props="Heavy, Reach, Two-handed",
      desc="A blade on the end of a long pole, effective at keeping enemies at distance."),
    i("Greataxe",           WP,"Martial Melee","blacksmith,weaponsmith",          30,  7,
      dmg="1d12", dmg_type="slashing", props="Heavy, Two-handed",
      desc="A massive double-headed axe. Favored by barbarians for maximum carnage."),
    i("Greatsword",         WP,"Martial Melee","blacksmith,weaponsmith",          50,  6,
      dmg="2d6", dmg_type="slashing", props="Heavy, Two-handed",
      desc="A massive sword requiring two hands. The pinnacle of blade craftsmanship."),
    i("Halberd",            WP,"Martial Melee","blacksmith,weaponsmith",          20,  6,
      dmg="1d10", dmg_type="slashing", props="Heavy, Reach, Two-handed",
      desc="An axe blade topped with a spike, mounted on a long pole. Versatile polearm."),
    i("Lance",              WP,"Martial Melee","blacksmith,weaponsmith,stable",   10,  6,
      dmg="1d12", dmg_type="piercing", props="Reach, Special (disadvantage within 5 ft, one-handed mounted)",
      desc="A long cavalry weapon. Unwieldy on foot but devastating on horseback."),
    i("Longsword",          WP,"Martial Melee","blacksmith,weaponsmith",          15,  3,
      dmg="1d8", dmg_type="slashing", props="Versatile (1d10)",
      desc="The classic knight's sword, balanced for one or two hands."),
    i("Maul",               WP,"Martial Melee","blacksmith,weaponsmith",          10,  10,
      dmg="2d6", dmg_type="bludgeoning", props="Heavy, Two-handed",
      desc="A massive two-handed hammer. Brutally effective against armored opponents."),
    i("Morningstar",        WP,"Martial Melee","blacksmith,weaponsmith",          15,  4,
      dmg="1d8", dmg_type="piercing", props="—",
      desc="A spiked ball atop a handle. Punches through chain and plate armor."),
    i("Pike",               WP,"Martial Melee","blacksmith,weaponsmith",           5,  18,
      dmg="1d10", dmg_type="piercing", props="Heavy, Reach, Two-handed",
      desc="A very long spear used in infantry formations to counter cavalry charges."),
    i("Rapier",             WP,"Martial Melee","blacksmith,weaponsmith",          25,   2,
      dmg="1d8", dmg_type="piercing", props="Finesse",
      desc="A slender thrusting blade favored by duelists and rogue-types."),
    i("Scimitar",           WP,"Martial Melee","blacksmith,weaponsmith",          25,   3,
      dmg="1d6", dmg_type="slashing", props="Finesse, Light",
      desc="A curved single-edged blade. Fast and light, ideal for dual-wielding."),
    i("Shortsword",         WP,"Martial Melee","blacksmith,weaponsmith",          10,   2,
      dmg="1d6", dmg_type="piercing", props="Finesse, Light",
      desc="A short double-edged blade. Favored by rogues and fighters in tight spaces."),
    i("Trident",            WP,"Martial Melee","blacksmith,weaponsmith",           5,   4,
      dmg="1d6", dmg_type="piercing", props="Thrown (20/60 ft), Versatile (1d8)",
      desc="A three-pronged spear associated with sea gods and gladiators."),
    i("War Pick",           WP,"Martial Melee","blacksmith,weaponsmith",           5,   2,
      dmg="1d8", dmg_type="piercing", props="—",
      desc="A pick-headed weapon designed to punch through plate armor."),
    i("Warhammer",          WP,"Martial Melee","blacksmith,weaponsmith",          15,   2,
      dmg="1d8", dmg_type="bludgeoning", props="Versatile (1d10)",
      desc="A heavy-headed hammer for battle. One- or two-handed. Clerics' martial weapon of choice."),
    i("Whip",               WP,"Martial Melee","general,weaponsmith",              2,   3,
      dmg="1d4", dmg_type="slashing", props="Finesse, Reach",
      desc="A long flexible lash. Can strike foes up to 10 ft away."),

    # ══════════════════════════════════════════════════════════════════════════
    # WEAPONS — Martial Ranged
    # ══════════════════════════════════════════════════════════════════════════

    i("Blowgun",            WP,"Martial Ranged","fletcher,weaponsmith,exotic",    10,   1,
      dmg="1", dmg_type="piercing", props="Ammunition (25/100 ft), Loading",
      desc="A hollow tube used to fire small needles. Silent and easy to conceal. Often used with poison."),
    i("Hand Crossbow",      WP,"Martial Ranged","fletcher,weaponsmith,blacksmith",75,   3,
      dmg="1d6", dmg_type="piercing", props="Ammunition (30/120 ft), Light, Loading",
      desc="A small one-handed crossbow. Favored by rogues who want a ranged option in their off-hand."),
    i("Heavy Crossbow",     WP,"Martial Ranged","fletcher,weaponsmith,blacksmith",50,  18,
      dmg="1d10", dmg_type="piercing", props="Ammunition (100/400 ft), Heavy, Loading, Two-handed",
      desc="A powerful mechanical bow with excellent range and penetration. Slow to reload."),
    i("Longbow",            WP,"Martial Ranged","fletcher,weaponsmith",           50,   2,
      dmg="1d8", dmg_type="piercing", props="Ammunition (150/600 ft), Heavy, Two-handed",
      desc="A tall wooden bow, taller than a man. The weapon of choice for trained archers."),
    i("Net",                WP,"Martial Ranged","fletcher,weaponsmith,general",    1,   3,
      dmg="—",  dmg_type="—",        props="Thrown (5/15 ft), Special (Large or smaller creature restrained)",
      desc="Thrown to entangle a foe. A restrained creature can use an action to make DC 10 STR check to escape."),

    # ══════════════════════════════════════════════════════════════════════════
    # AMMUNITION
    # ══════════════════════════════════════════════════════════════════════════

    i("Arrows (20)",           WP,"Ammunition","fletcher,general,outfitter",  1,   1,
      desc="Standard arrows for shortbows and longbows. Recoverable after combat."),
    i("Blowgun Needles (50)",  WP,"Ammunition","fletcher,exotic",             1,   1,
      desc="Thin needles fired from a blowgun. Often coated in poison."),
    i("Crossbow Bolts (20)",   WP,"Ammunition","fletcher,general,blacksmith", 1, 1.5,
      desc="Short, thick bolts for light or heavy crossbows."),
    i("Sling Bullets (20)",    WP,"Ammunition","general,fletcher",            0.04, 1.5,
      desc="Lead or stone balls for slings. Recoverable after combat."),

    # ══════════════════════════════════════════════════════════════════════════
    # ADVENTURING GEAR
    # ══════════════════════════════════════════════════════════════════════════

    i("Abacus",              GR,"Gear","general,scribe",             2,    2,    desc="A counting frame of beads on rods. Useful for merchants and accountants."),
    i("Acid (vial)",         GR,"Gear","alchemist",                 25,    1,    desc="As an action, splash on creature within 5 ft or throw 20 ft. 2d6 acid damage on hit; 1d6 on nearby splash."),
    i("Alchemist's Fire",    GR,"Gear","alchemist",                 50,    1,    desc="Sticky, adhesive fluid that ignites on air contact. Target takes 1d4 fire damage/round until they use action to make DC 10 DEX check to extinguish."),
    i("Antitoxin (vial)",    GR,"Gear","alchemist,general",         50,    0,    desc="A creature that drinks antitoxin has advantage on CON saves against poison for 1 hour."),
    i("Arcane Focus (Crystal)",GR,"Gear","general,scribe",          10,    1,    desc="A specially crafted crystal used by sorcerers and wizards as a spellcasting focus."),
    i("Arcane Focus (Orb)",  GR,"Gear","general,scribe",            20,    3,    desc="A polished orb used as a spellcasting focus."),
    i("Arcane Focus (Rod)",  GR,"Gear","general,scribe",            10,    2,    desc="A metal rod engraved with arcane sigils, used as a spellcasting focus."),
    i("Arcane Focus (Staff)",GR,"Gear","general,scribe,outfitter",   5,    4,    desc="A wooden staff carved with mystical symbols, doubles as a walking staff."),
    i("Arcane Focus (Wand)", GR,"Gear","general,scribe",            10,    1,    desc="A slender rod of wood or metal, the classic wizard's spellcasting focus."),
    i("Backpack",            GR,"Gear","general,outfitter",          2,    5,    cap="30 lb / 1 cubic ft", desc="A leather sack with shoulder straps. Essential adventuring gear."),
    i("Ball Bearings (bag)", GR,"Gear","general,outfitter",          1,    2,    desc="Bag of 1,000 ball bearings. Pour over 10-ft square; creatures must make DC 10 DEX save or fall prone."),
    i("Barrel",              GR,"Gear","general,market",             2,   70,    cap="40 gallons liquid / 4 cubic ft solid", desc="A large wooden cask. Useful for storing and transporting goods."),
    i("Basket",              GR,"Gear","general,market",             0.4,  2,    cap="2 cubic ft / 40 lb", desc="A woven basket for carrying goods."),
    i("Bedroll",             GR,"Gear","general,outfitter",          1,    7,    desc="A padded roll of blankets for sleeping outdoors. Adds comfort to long travel."),
    i("Bell",                GR,"Gear","general,outfitter",          1,    0,    desc="A small metal bell, useful as a simple alarm trigger."),
    i("Blanket",             GR,"Gear","general,outfitter",          0.5,  3,    desc="A warm woolen blanket. Invaluable in cold climates."),
    i("Block and Tackle",    GR,"Gear","general,outfitter",          1,    5,    desc="A set of pulleys with a cable. Reduces the force needed to lift by half; max 1,000 lb."),
    i("Book",                GR,"Gear","scribe",                    25,    5,    desc="A blank book for writing, or filled with lore. Wizards use these as spellbooks."),
    i("Bottle, Glass",       GR,"Gear","general,alchemist",          2,    2,    cap="1.5 pints", desc="A glass bottle with a stopper. Used to hold potions and other liquids."),
    i("Bucket",              GR,"Gear","general",                    0.05, 2,    cap="3 gallons / 1/2 cubic ft", desc="A simple wooden or metal bucket."),
    i("Caltrops (bag of 20)",GR,"Gear","general,outfitter,weaponsmith",1,  2,   desc="Scatter over 5-ft square. First creature that enters must make DC 15 DEX save or stop moving and take 1 piercing damage. Speed halved until healed."),
    i("Candle",              GR,"Gear","general",                    0.01, 0,    desc="Sheds bright light in a 5-ft radius and dim light for another 5 ft for 1 hour."),
    i("Canteen",             GR,"Gear","general,outfitter",          0.2,  1,    cap="1 quart", desc="A metal container for carrying water."),
    i("Case, Crossbow Bolt", GR,"Gear","fletcher,general,outfitter", 1,    1,    cap="20 bolts", desc="A leather case for crossbow bolts."),
    i("Case, Map or Scroll", GR,"Gear","general,scribe,outfitter",   1,    1,    desc="A rigid tube of leather or bone for protecting rolled maps and scrolls."),
    i("Chain (10 ft)",       GR,"Gear","blacksmith,general",         5,   10,    desc="A metal chain. Has AC 19 and can hold up to 10 STR check DC 20 to break."),
    i("Chalk (1 piece)",     GR,"Gear","general,scribe",             0.01, 0,    desc="Used for writing on stone or wood. Leaves an easily visible mark."),
    i("Chest",               GR,"Gear","general,outfitter",          5,   25,    cap="12 cubic ft / 300 lb", desc="A sturdy wooden chest with lock. Standard for storing valuables."),
    i("Clothes, Common",     GR,"Clothing","general,clothier",       0.5,  3,    desc="Plain everyday clothes: shirt, trousers, shoes, and cloak. Worn by commoners."),
    i("Clothes, Costume",    GR,"Clothing","clothier,general",       5,    4,    desc="Theatrical garments for performers or anyone needing a disguise."),
    i("Clothes, Fine",       GR,"Clothing","clothier,jeweler",      15,    6,    desc="Elegant garments of quality fabric, trimmed with embroidery. Required for noble courts."),
    i("Clothes, Traveler's", GR,"Clothing","general,outfitter,clothier",2, 4,   desc="Sturdy, practical travel wear: layered wool, thick boots, and a weatherproof cloak."),
    i("Component Pouch",     GR,"Gear","general,alchemist,outfitter",25,   2,    desc="A small waterproof pouch containing material spell components (excluding those with a gold cost)."),
    i("Crowbar",             GR,"Gear","blacksmith,general,outfitter",2,   5,    desc="A metal pry bar. Grants advantage on STR checks where leverage could help."),
    i("Druidic Focus (Mistletoe)",GR,"Gear","general,outfitter",     1,    0,    desc="A sprig of mistletoe used by druids as a spellcasting focus."),
    i("Druidic Focus (Totem)",GR,"Gear","general,exotic",            1,    0,    desc="An animal totem used as a druidic spellcasting focus."),
    i("Druidic Focus (Wooden Staff)",GR,"Gear","general,outfitter",  5,    4,    desc="A staff carved from a living branch; used as a druidic spellcasting focus."),
    i("Druidic Focus (Yew Wand)",GR,"Gear","general,scribe",        10,    1,    desc="A wand of yew wood, carved with natural symbols. Druidic spellcasting focus."),
    i("Fishing Tackle",      GR,"Gear","general,outfitter",          1,    4,    desc="A hook, line, floats, and a small net. Useful for supplementing rations in the wild."),
    i("Flask or Tankard",    GR,"Gear","general",                    0.02, 1,    cap="1 pint", desc="A metal or ceramic drinking vessel."),
    i("Grappling Hook",      GR,"Gear","blacksmith,outfitter,general",2,   4,   desc="A multi-pronged metal hook attached to a rope. Used for climbing or catching ledges."),
    i("Hammer",              GR,"Gear","blacksmith,general,outfitter",1,   3,    desc="A standard hammer for driving pitons, nails, and similar tasks."),
    i("Hammer, Sledge",      GR,"Gear","blacksmith,general",         2,   10,    desc="A large two-handed hammer for breaking stone, driving stakes, or battering down doors."),
    i("Healer's Kit",        GR,"Gear","general,alchemist,outfitter", 5,   3,    desc="10 uses. As an action, stabilize a creature at 0 HP without a Medicine check. Also useful for tending wounds."),
    i("Holy Symbol (Amulet)",GR,"Gear","general",                    5,    1,    desc="A metal amulet embossed with the symbol of a deity. Cleric/paladin spellcasting focus."),
    i("Holy Symbol (Emblem)",GR,"Gear","blacksmith",                 5,    0,    desc="A religious symbol embossed on a shield or armor. Functions as a spellcasting focus."),
    i("Holy Symbol (Reliquary)",GR,"Gear","general",                 5,    2,    desc="A small box containing a holy relic. Cleric/paladin spellcasting focus."),
    i("Holy Water (flask)",  GR,"Gear","general,alchemist",         25,    1,    desc="As an action, splash on creature within 5 ft or throw 20 ft. Deals 2d6 radiant damage to undead and fiends."),
    i("Hourglass",           GR,"Gear","general,scribe",            25,    1,    desc="Measures one hour as fine sand flows from top to bottom chamber."),
    i("Hunting Trap",        GR,"Gear","general,outfitter",          5,   25,    desc="A serrated steel trap. DC 13 DEX save when stepped on or restrained. STR DC 13 to escape; 1d4 piercing damage on failure."),
    i("Ink (1-oz bottle)",   GR,"Gear","scribe",                    10,    0,    desc="A bottle of writing ink. Enough for several pages of script."),
    i("Ink Pen",             GR,"Gear","scribe,general",             0.02, 0,    desc="A quill or reed pen for writing with ink."),
    i("Jug or Pitcher",      GR,"Gear","general",                    0.02, 4,    cap="1 gallon", desc="A ceramic or metal jug for liquids."),
    i("Ladder (10 ft)",      GR,"Gear","general,outfitter",          0.1, 25,    desc="A simple wooden ladder. Useful in dungeons where rope isn't enough."),
    i("Lamp",                GR,"Gear","general,outfitter",          0.5,  1,    desc="Bright light 15-ft radius, dim light 30 ft. Burns for 6 hours per pint of oil."),
    i("Lantern, Bullseye",   GR,"Gear","general,outfitter",         10,    2,    desc="Casts bright light in a 60-ft cone, dim light for another 60 ft. Burns for 6 hours per pint of oil."),
    i("Lantern, Hooded",     GR,"Gear","general,outfitter",          5,    2,    desc="Bright light 30-ft radius, dim light 30 ft. Can be shuttered to dim to 5-ft dim light only."),
    i("Lock",                GR,"Gear","blacksmith,general",        10,    1,    desc="Comes with a key. DC 15 thieves' tools check to pick."),
    i("Magnifying Glass",    GR,"Gear","scribe,jeweler",           100,    0,    desc="Focuses sunlight to start a fire in a minute. Grants advantage on appraisal checks. Required for some alchemical tasks."),
    i("Manacles",            GR,"Gear","blacksmith,general",         2,    6,    desc="Shackle a Medium or smaller creature. Escape DC 20 DEX (thieves' tools) or DC 20 STR. AC 19, 15 HP."),
    i("Mirror, Steel",       GR,"Gear","blacksmith,general,outfitter",5,  0.5,  desc="A polished steel mirror. Useful for seeing around corners, checking for basilisks, and signaling."),
    i("Oil (flask)",         GR,"Gear","general,outfitter",          0.1,  1,    desc="Fuel for lanterns (6 hours per flask). Can also be used offensively — splash for 5 fire damage if lit."),
    i("Paper (sheet)",       GR,"Gear","scribe,general",             0.2,  0,    desc="A sheet of fine paper. Lighter and easier to write on than parchment."),
    i("Parchment (sheet)",   GR,"Gear","scribe,general",             0.1,  0,    desc="A sheet of treated animal skin, used for writing or drawing maps."),
    i("Perfume (vial)",      GR,"Gear","general,clothier,jeweler",   5,    0,    desc="A small vial of fragrant perfume or cologne."),
    i("Pick, Miner's",       GR,"Gear","blacksmith,general,outfitter",2,  10,   desc="A heavy-headed pick for breaking rock. Also useful for making handholds in stone walls."),
    i("Piton",               GR,"Gear","blacksmith,outfitter,general",0.05, 0.25,desc="A metal spike driven into stone to anchor a rope. Usually sold in bundles of 10."),
    i("Poison, Basic (vial)",GR,"Gear","alchemist",                100,    0,    desc="Apply to weapon or ammo. First creature hit must make DC 10 CON save or take 1d4 poison damage and be poisoned for 1 minute."),
    i("Pole (10 ft)",        GR,"Gear","general,outfitter",          0.05, 7,    desc="A 10-ft wooden pole. Useful for prodding suspicious floors, propping doors, or vaulting over gaps."),
    i("Pot, Iron",           GR,"Gear","general,outfitter",          2,   10,    cap="1 gallon", desc="A sturdy iron cooking pot. Essential for making camp meals."),
    i("Pouch",               GR,"Gear","general,clothier",           0.5,  1,    cap="1/5 cubic ft / 6 lb", desc="A small leather belt pouch. Holds coins, components, and small items."),
    i("Quiver",              GR,"Gear","fletcher,general,outfitter",  1,   1,    cap="20 arrows or bolts", desc="A cylindrical case worn on the back or belt for carrying ammunition."),
    i("Ram, Portable",       GR,"Gear","blacksmith,outfitter",        4,  35,    desc="A heavy metal ram for bashing down doors. Grants +4 to STR checks to break down doors; two wielders grant advantage."),
    i("Rations (1 day)",     GR,"Gear","general,outfitter",          0.5,  2,    desc="Hard tack, dried meat, dried fruit, and nuts. No preparation required. 1 day's worth of food."),
    i("Robes",               GR,"Clothing","clothier,general",        1,   4,    desc="A long flowing garment favored by scholars, clerics, and wizards."),
    i("Rope, Hempen (50 ft)",GR,"Gear","general,outfitter",           1,  10,    desc="Standard rope. Can hold up to 500 lb. Has AC 11 and 2 HP. DC 17 STR to break."),
    i("Rope, Silk (50 ft)",  GR,"Gear","outfitter,clothier",         10,   5,    desc="Lighter and stronger than hemp. DC 20 STR to break. Useful for thieves and climbers."),
    i("Sack",                GR,"Gear","general",                    0.01, 0.5,  cap="1 cubic ft / 30 lb", desc="A simple cloth or burlap bag."),
    i("Scale, Merchant's",   GR,"Gear","general,market",              5,   3,    desc="A small balance with weights. Required for precise measurement of coins and goods."),
    i("Sealing Wax",         GR,"Gear","scribe,general",              0.5, 0,    desc="Used with a signet ring to seal letters and documents."),
    i("Shovel",              GR,"Gear","blacksmith,general,outfitter", 2,   5,   desc="An iron-bladed digging tool. Essential for setting up camp and burying the dead."),
    i("Signal Whistle",      GR,"Gear","general,outfitter",           0.05, 0,  desc="A small metal whistle. Audible up to 600 ft in open terrain."),
    i("Signet Ring",         GR,"Gear","jeweler,general",             5,    0,   desc="A ring bearing a family or organizational crest, used to seal documents with wax."),
    i("Soap",                GR,"Gear","general",                     0.02, 0,   desc="A bar of lye soap. Useful for cleaning and potentially other alchemical tasks."),
    i("Spellbook",           GR,"Gear","scribe",                     50,   3,    desc="An ornate book of blank vellum pages (100 pages). Wizards use these to record their spells. Copied spells cost 50 gp and 2 hours per spell level."),
    i("Spikes, Iron (10)",   GR,"Gear","blacksmith,outfitter",        1,   5,    desc="Heavy iron spikes. Used for spiking doors shut, creating handholds, or improvising traps."),
    i("Spyglass",            GR,"Gear","scribe,jeweler,outfitter",  1000,  1,    desc="Magnifies objects up to 5× at a distance. Useful for scouts and navigators."),
    i("Tent, Two-Person",    GR,"Gear","general,outfitter",           2,   20,   desc="A simple canvas shelter for two. Provides protection from the elements on the road."),
    i("Tinderbox",           GR,"Gear","general,outfitter",           0.5,  1,   desc="Contains flint, fire steel, and tinder. Start a fire in 1 action (or 1 minute in wind). Lights a torch in 1 action."),
    i("Torch",               GR,"Gear","general,outfitter",           0.01, 1,   desc="Bright light 20-ft radius, dim light 20 ft. Burns 1 hour. Can be used as an improvised weapon (1 fire damage)."),
    i("Vial",                GR,"Gear","general,alchemist",           1,    0,   cap="4 ounces", desc="A small glass bottle with a cork stopper. Used for potions and alchemical reagents."),
    i("Waterskin",           GR,"Gear","general,outfitter",           0.2,  5,   cap="4 pints", desc="A leather bladder for carrying water. Full capacity provides roughly 4 days of survival water."),
    i("Whetstone",           GR,"Gear","blacksmith,general",          0.01, 1,   desc="A rough stone for sharpening bladed weapons."),

    # ══════════════════════════════════════════════════════════════════════════
    # EQUIPMENT PACKS
    # ══════════════════════════════════════════════════════════════════════════

    i("Burglar's Pack",      PK,"Equipment Pack","outfitter,general",  16,  0,
      desc="Includes a backpack, bag of 1000 ball bearings, 10 ft string, bell, 5 candles, crowbar, hammer, 10 pitons, hooded lantern, 2 flasks oil, 5 days rations, tinderbox, waterskin, and 50 ft hempen rope."),
    i("Diplomat's Pack",     PK,"Equipment Pack","outfitter,general",  39,  0,
      desc="Includes a chest, 2 scroll cases, fine clothes, bottle of ink, pen, lamp, 2 flasks oil, 5 sheets paper, vial perfume, sealing wax, and soap."),
    i("Dungeoneer's Pack",   PK,"Equipment Pack","outfitter,general",  12,  0,
      desc="Includes a backpack, crowbar, hammer, 10 pitons, 10 torches, tinderbox, 10 days rations, waterskin, and 50 ft hempen rope."),
    i("Entertainer's Pack",  PK,"Equipment Pack","outfitter,general",  40,  0,
      desc="Includes a backpack, bedroll, 2 costumes, 5 candles, 5 days rations, waterskin, and a disguise kit."),
    i("Explorer's Pack",     PK,"Equipment Pack","outfitter,general",  10,  0,
      desc="Includes a backpack, bedroll, mess kit, tinderbox, 10 torches, 10 days rations, waterskin, and 50 ft hempen rope."),
    i("Priest's Pack",       PK,"Equipment Pack","outfitter,general",  19,  0,
      desc="Includes a backpack, blanket, 10 candles, tinderbox, alms box, 2 blocks incense, censer, vestments, 2 days rations, waterskin."),
    i("Scholar's Pack",      PK,"Equipment Pack","outfitter,scribe",   40,  0,
      desc="Includes a backpack, book of lore, bottle of ink, ink pen, 10 sheets parchment, small bag of sand, and small knife."),

    # ══════════════════════════════════════════════════════════════════════════
    # TOOLS — Artisan Tools
    # ══════════════════════════════════════════════════════════════════════════

    i("Alchemist's Supplies",   TL,"Artisan Tool","alchemist,blacksmith",   50,  8, desc="Two glass beakers, a metal frame, rubber tubing, and a variety of alchemical reagents. Required for brewing potions and identifying substances."),
    i("Brewer's Supplies",      TL,"Artisan Tool","general,market",          20,  9, desc="A large jug, hops, siphon, and several pouches of herbs. Required for brewing ales and mead."),
    i("Calligrapher's Supplies",TL,"Artisan Tool","scribe",                  10,  5, desc="Inks, parchment, and specialized quills for ornate writing."),
    i("Carpenter's Tools",      TL,"Artisan Tool","general,blacksmith",       8,  6, desc="Saw, hammer, nails, chisel, and adze. Used for building and repairing wooden structures."),
    i("Cartographer's Tools",   TL,"Artisan Tool","scribe,outfitter",        15,  6, desc="Pens, ink, measuring instruments, and blank paper for drawing maps."),
    i("Cobbler's Tools",        TL,"Artisan Tool","general,clothier",         5,  5, desc="A hammer, awl, knife, leather scraps, and thread for making and repairing footwear."),
    i("Cook's Utensils",        TL,"Artisan Tool","general,outfitter",        1,  8, desc="A metal pot, ladle, cutting knife, fork, stirring spoon, and skillet."),
    i("Glassblower's Tools",    TL,"Artisan Tool","alchemist,market",        30,  5, desc="A blowpipe and shaping tools for crafting glass items."),
    i("Jeweler's Tools",        TL,"Artisan Tool","jeweler",                 25,  2, desc="Small hammer, files, pliers, tweezers, a small magnifying glass, and setting tools."),
    i("Leatherworker's Tools",  TL,"Artisan Tool","general,clothier",         5,  5, desc="Knife, needles, thread, and dyes for working with leather."),
    i("Mason's Tools",          TL,"Artisan Tool","general,blacksmith",      10,  8, desc="A trowel, hammer, chisel, brushes, and whetstones for working with stone."),
    i("Painter's Supplies",     TL,"Artisan Tool","scribe,general",          10,  5, desc="Easel, canvas, paint brushes, charcoal sticks, and a palette."),
    i("Potter's Tools",         TL,"Artisan Tool","general,market",          10,  3, desc="Potter's needles, loop tools, wire end tools, and scrapers."),
    i("Smith's Tools",          TL,"Artisan Tool","blacksmith",              20,  8, desc="Hammers, tongs, charcoal, rags, and a whetstone for working metal."),
    i("Tinker's Tools",         TL,"Artisan Tool","blacksmith,general",      50, 10, desc="A variety of hand tools, thread, needles, a whetstone, scraps of cloth and leather, and small leather pouches."),
    i("Weaver's Tools",         TL,"Artisan Tool","clothier,general",         1,  5, desc="Thread, needle, and scraps of cloth."),
    i("Woodcarver's Tools",     TL,"Artisan Tool","general,outfitter",        1,  5, desc="A knife, a gouge, and a small saw for carving wood."),

    # ── Gaming Sets ──────────────────────────────────────────────────────────
    i("Dice Set",               TL,"Gaming Set","general",                0.1,  0, desc="A set of polyhedral dice used for games of chance."),
    i("Dragonchess Set",        TL,"Gaming Set","general,jeweler",          1, 0.5,desc="A chess-like strategy game played on a three-tiered board with 40 pieces per side."),
    i("Playing Card Set",       TL,"Gaming Set","general",                0.5,  0, desc="A deck of cards for various gambling and parlor games."),
    i("Three-Dragon Ante Set",  TL,"Gaming Set","general",                  1,  0, desc="A card game popular in taverns across the Realms. Players wager on the outcome."),

    # ── Musical Instruments ──────────────────────────────────────────────────
    i("Bagpipes",               TL,"Musical Instrument","instrument,general",30, 6, desc="A wind instrument using enclosed reeds fed from a constant air supply."),
    i("Drum",                   TL,"Musical Instrument","instrument,general",  6, 3, desc="A percussion instrument played with sticks or hands."),
    i("Dulcimer",               TL,"Musical Instrument","instrument",         25,10, desc="A stringed instrument played by striking strings with padded hammers."),
    i("Flute",                  TL,"Musical Instrument","instrument,general",  2, 1, desc="A simple wind instrument made from bone or wood."),
    i("Horn",                   TL,"Musical Instrument","instrument,general",  3, 2, desc="A wind instrument made from animal horn. Audible up to 600 ft outdoors."),
    i("Lute",                   TL,"Musical Instrument","instrument",         35, 2, desc="The quintessential bard's instrument. Six paired strings over a pear-shaped body."),
    i("Lyre",                   TL,"Musical Instrument","instrument",         30, 2, desc="A small harp-like instrument associated with bardic tradition and divine inspiration."),
    i("Pan Flute",              TL,"Musical Instrument","instrument,general", 12, 2, desc="A series of graduated pipes tied together, played by blowing across the open ends."),
    i("Shawm",                  TL,"Musical Instrument","instrument,general",  2, 1, desc="A loud, double-reed wind instrument, the ancestor of the oboe."),
    i("Viol",                   TL,"Musical Instrument","instrument",         30, 1, desc="A bowed stringed instrument held between the legs. Produces a rich, resonant tone."),

    # ── Other Tools ──────────────────────────────────────────────────────────
    i("Disguise Kit",           TL,"Tool","general,clothier,outfitter",   25, 3, desc="Cosmetics, hair dye, small props, and other items. Used for the Disguise Self skill."),
    i("Forgery Kit",            TL,"Tool","scribe",                       15, 5, desc="Multiple inks, parchment, quills, seals, and wax. Used for creating convincing forgeries."),
    i("Herbalism Kit",          TL,"Tool","alchemist,general",             5, 3, desc="Pouches, clippers, leather gloves, and vials. Required to identify and apply herbal remedies. Can create antitoxin and healing potions."),
    i("Navigator's Tools",      TL,"Tool","outfitter,shipwright",         25, 2, desc="Sextant, compass, calipers, ruler, parchment, ink, and quill. Required for navigation at sea or in the wilderness."),
    i("Poisoner's Kit",         TL,"Tool","alchemist",                    50, 2, desc="Glass vials, a mortar and pestle, chemical reagents, and assorted tools. For crafting poisons."),
    i("Thieves' Tools",         TL,"Tool","general,outfitter",            25, 1, desc="A small file, lock picks, a small mirror, narrow-bladed scissors, and pliers. Required for picking locks and disabling traps."),

    # ══════════════════════════════════════════════════════════════════════════
    # MOUNTS & ANIMALS
    # ══════════════════════════════════════════════════════════════════════════

    i("Camel",                  MT,"Mount","stable",                      50,  0, cap="480 lb",  spd="50 ft", desc="A desert mount with great endurance. Can go without water for 8 days. Carries up to 480 lb."),
    i("Donkey / Mule",          MT,"Beast of Burden","stable,general",     8,  0, cap="420 lb",  spd="40 ft", desc="A sturdy pack animal. Cannot be used as a combat mount. Can carry 420 lb and pull twice that."),
    i("Elephant",               MT,"Mount","exotic",                     200,  0, cap="1320 lb", spd="40 ft", desc="A massive beast of burden or war mount. Only available from exotic dealers. Requires special training to ride."),
    i("Horse, Draft",           MT,"Beast of Burden","stable",            50,  0, cap="540 lb",  spd="40 ft", desc="A large, powerful horse bred for hauling and farming. Not suitable as a combat mount."),
    i("Horse, Riding",          MT,"Mount","stable",                      75,  0, cap="480 lb",  spd="60 ft", desc="The standard adventurer's mount. Reliable, trainable, and widely available. Carries 480 lb."),
    i("Mastiff",                MT,"Animal","stable,general",             25,  0, cap="195 lb",  spd="40 ft", desc="A large guard dog. Can be trained to attack. Used as a mount by halflings and gnomes."),
    i("Pony",                   MT,"Mount","stable,general",              30,  0, cap="225 lb",  spd="40 ft", desc="A small horse suitable for Small races. Reliable and easy to manage."),
    i("Warhorse",               MT,"Mount","stable",                     400,  0, cap="540 lb",  spd="60 ft", desc="A trained combat mount. Proficient in attack and unafraid of battle. Carries 540 lb."),
    i("Ox",                     MT,"Beast of Burden","stable,market",     15,  0, cap="900 lb",  spd="30 ft", desc="Powerful work animal for pulling plows and heavy loads. Provides 900 lb of pulling power."),
    i("Goat",                   MT,"Animal","stable,market",               1,  0, cap="75 lb",   spd="40 ft", desc="Hardy animal used for milk, meat, and wool. Can carry light packs in a pinch."),
    i("Pig",                    MT,"Animal","stable,market",               3,  0, desc="A domestic swine raised for meat. Found on farms throughout the realm."),
    i("Chicken",                MT,"Animal","stable,general,market",   0.02,  0, desc="A domestic fowl raised for eggs and meat."),
    i("Cow",                    MT,"Animal","stable,market",              10,  0, desc="A dairy and beef cattle animal. Vital to agricultural economies."),
    i("Dog, Guard",             MT,"Animal","stable,general",              5,  0, spd="40 ft",  desc="A trained watchdog that barks at intruders and can attack on command."),
    i("Hawk",                   MT,"Animal","stable,exotic",              50,  0, spd="60 ft flying", desc="A trained hunting bird. Can be sent to attack small prey or deliver messages."),
    i("Raven",                  MT,"Animal","exotic,stable",               1,  0, spd="50 ft flying", desc="An intelligent corvid that can be trained to mimic short phrases."),

    # ══════════════════════════════════════════════════════════════════════════
    # TACK, HARNESS & DRAWN VEHICLES
    # ══════════════════════════════════════════════════════════════════════════

    i("Bit and Bridle",         VH,"Tack","stable",                       2,  1,  desc="A metal bit and leather bridle for controlling a mount. Required for most riding."),
    i("Feed (per day)",         MT,"Animal Supplies","stable,general",    0.05,10, desc="Feed grain for one horse, mule, or other similar-sized animal for one day."),
    i("Saddle, Exotic",         VH,"Tack","stable,exotic",               60, 40,  cap="—", desc="A specialized saddle for unusual mounts (hippogriff, griffon, etc.). Keeps the rider secure in aerial maneuvers."),
    i("Saddle, Military",       VH,"Tack","stable,blacksmith",           20, 30,  desc="A deep-seated saddle that keeps the rider secure during combat. Advantage on checks to stay mounted."),
    i("Saddle, Pack",           VH,"Tack","stable,general",               5, 15,  cap="—", desc="A frame and harness for securing pack loads to an animal. Required for pack animals."),
    i("Saddle, Riding",         VH,"Tack","stable",                      10, 25,  desc="The standard riding saddle. Comfortable for long journeys."),
    i("Saddlebags",             VH,"Tack","stable,outfitter",             4,  8,  cap="20 lb each side", desc="A pair of leather bags that hang across a mount's flanks. Holds 20 lb per side."),
    i("Stabling (per day)",     VH,"Animal Supplies","stable",            0.5, 0, desc="The cost of boarding one mount for one day: stall, feed, water, and basic grooming."),
    i("Cart",                   VH,"Drawn Vehicle","stable",             15, 200,  cap="200 lb", spd="30 ft (pulled)", desc="A simple two-wheeled cart pulled by one animal. Carries 200 lb of cargo."),
    i("Carriage",               VH,"Drawn Vehicle","stable",            100, 600,  cap="4 passengers + 600 lb cargo", spd="30 ft (pulled)", desc="An enclosed four-wheeled passenger vehicle. Requires two horses. Comfortable for long journeys."),
    i("Chariot",                VH,"Drawn Vehicle","stable,blacksmith", 250, 100,  cap="2 riders", spd="50 ft (pulled)", desc="A light two-wheeled combat vehicle. Requires one or two war-trained horses. Riders can attack from it."),
    i("Sled",                   VH,"Drawn Vehicle","stable",             20, 300,  cap="300 lb", spd="40 ft on snow/ice", desc="A flat-bottomed vehicle on runners for travel across snow and ice. Pulled by dogs or a horse."),
    i("Wagon",                  VH,"Drawn Vehicle","stable,market",      35, 400,  cap="400 lb", spd="30 ft (pulled)", desc="A large four-wheeled freight vehicle. Requires two draft horses. The standard for merchants and settlers."),

    # ══════════════════════════════════════════════════════════════════════════
    # WATERBORNE VEHICLES
    # ══════════════════════════════════════════════════════════════════════════

    i("Rowboat",                VH,"Waterborne Vehicle","shipwright,stable", 50,   0, cap="600 lb", spd="1.5 mph", desc="A small open boat powered by oars. Holds 3 passengers or equivalent cargo."),
    i("Keelboat",               VH,"Waterborne Vehicle","shipwright",      3000,   0, cap="1/2 ton", spd="1 mph upstream / 3 mph downstream", desc="A flat-bottomed river vessel that can be poled, rowed, or sailed. Crew of 1-2; carries half a ton."),
    i("Sailing Ship",           VH,"Waterborne Vehicle","shipwright",     10000,   0, cap="100 tons", spd="2 mph", desc="A medium ocean-going vessel with multiple masts. Crew of 20, up to 20 passengers, 100 tons of cargo."),
    i("Longship",               VH,"Waterborne Vehicle","shipwright",     10000,   0, cap="10 tons", spd="3 mph", desc="A Norse-style vessel suited for both sea and river travel. Crew of 40 rowers; can beach directly on shore."),
    i("Warship",                VH,"Waterborne Vehicle","shipwright",     25000,   0, cap="200 tons", spd="2.5 mph", desc="A large military vessel equipped with a ram, ballistas, and a full complement of marines. Crew of 60+."),
    i("Galley",                 VH,"Waterborne Vehicle","shipwright",     30000,   0, cap="150 tons", spd="4 mph", desc="A large oar-driven warship. Crew of 80 rowers plus soldiers. Used for naval warfare and blockades."),

    # ══════════════════════════════════════════════════════════════════════════
    # TRADE GOODS
    # ══════════════════════════════════════════════════════════════════════════

    i("Wheat (1 lb)",           TG,"Foodstuff","market,general",           0.01, 1, desc="Staple grain. Basis of bread and most common food in the realm."),
    i("Flour (1 lb)",           TG,"Foodstuff","market,general",           0.02, 1, desc="Ground wheat. Ready for baking bread, pies, and other staples."),
    i("Salt (1 lb)",            TG,"Foodstuff","market,general",           0.05, 1, desc="Essential for preserving meat and flavoring food. Also has ritual uses."),
    i("Sugar (1 lb)",           TG,"Foodstuff","market,general",           0.1,  1, desc="Refined sweetener. A luxury in most settlements outside tropical regions."),
    i("Tea (1 lb)",             TG,"Foodstuff","market,general",           0.5,  1, desc="Dried tea leaves from distant lands. Brewed as a warm beverage."),
    i("Ginger (1 lb)",          TG,"Spice","market",                        1,   1, desc="A pungent spice used in cooking and medicine. Imported from southern lands."),
    i("Cinnamon (1 lb)",        TG,"Spice","market",                        2,   1, desc="A sweet-smelling spice. Valuable because it must be imported from distant tropical regions."),
    i("Pepper (1 lb)",          TG,"Spice","market",                        2,   1, desc="The most traded spice in the realm. Used as both seasoning and currency in some regions."),
    i("Cloves (1 lb)",          TG,"Spice","market",                       15,   1, desc="Extremely aromatic dried flower buds from tropical trees. Used in cooking, medicine, and perfumery."),
    i("Saffron (1 lb)",         TG,"Spice","market",                       15,   1, desc="The world's most expensive spice by weight. Harvested from a particular crocus flower."),
    i("Canvas (1 sq. yd.)",     TG,"Textile","market,outfitter",           0.1,  1, desc="Heavy woven fabric. Used for sails, tents, and sacks."),
    i("Cotton Cloth (1 sq. yd.)",TG,"Textile","market,clothier",           0.5,  1, desc="Lightweight woven cotton. Used for clothing, bandages, and bedding."),
    i("Linen (1 sq. yd.)",      TG,"Textile","market,clothier",             5,   1, desc="High-quality cloth woven from flax fibers. Prized for fine garments."),
    i("Silk (1 sq. yd.)",       TG,"Textile","market,clothier,jeweler",    10,   1, desc="Luxuriously smooth fabric produced by silkworms. Only the wealthy can afford silk garments."),
    i("Wool (1 lb)",            TG,"Textile","market,clothier,general",    0.1,  1, desc="Raw wool fiber. Spun into thread, woven into cloth, or used as batting."),
    i("Iron (1 lb)",            TG,"Raw Material","market,blacksmith",     0.1,  1, desc="Raw iron ore or refined iron bars. The most common metalworking material."),
    i("Copper (1 lb)",          TG,"Raw Material","market,jeweler",          5,  1, desc="A red metal used for coins, pipes, and alloyed with tin to make bronze."),
    i("Silver (1 lb)",          TG,"Raw Material","market,jeweler",         25,  1, desc="A valuable white metal. Used for coins, weapons effective against lycanthropes, and fine jewelry."),
    i("Gold (1 lb)",            TG,"Raw Material","market,jeweler",         50,  1, desc="The standard of wealth. Used for coins, jewelry, and some magical components."),
    i("Platinum (1 lb)",        TG,"Raw Material","market,jeweler",        500,  1, desc="An extremely rare heavy metal. Used only for the highest denomination coins."),
    i("Timber (per cord)",      TG,"Raw Material","market,general",          5, 0,  desc="A stacked cord (4×4×8 ft) of cut firewood or lumber. Used for building and heating."),
    i("Coal (per sack)",        TG,"Raw Material","market,blacksmith",       1, 20,  desc="A sack of coal for forges and furnaces. Burns hotter and longer than wood."),
]


def main():
    init_db()
    seeded = 0
    for item in ITEMS:
        upsert_mundane_item(item)
        seeded += 1

    total = count_mundane_items()
    print(f"Seeded {seeded} items ({total} total in DB).")

    import sqlite3, os
    db = os.path.join(os.path.dirname(__file__), "dnd_game.db")
    with sqlite3.connect(db) as con:
        rows = con.execute(
            "SELECT category, COUNT(*) as n FROM mundane_items GROUP BY category ORDER BY category"
        ).fetchall()
    for cat, cnt in rows:
        print(f"  {cat}: {cnt}")


if __name__ == "__main__":
    main()
