"""
seed_magic_items.py
Populates the magic_items reference table with SRD/DMG items.
Safe to re-run — uses upsert.

Usage:
    python seed_magic_items.py
"""

import sys
from db_manager import init_db, upsert_magic_item, count_magic_items

# ── Item data ───────────────────────────────────────────────────────────────────
# Fields: name, category, rarity, requires_attunement, attunement_by, effect,
#         stat_set_str/dex/con/int/wis/cha  (0 = no effect; >0 = sets score to value),
#         stat_bonus_str/dex/con/int/wis/cha (flat bonus added to score),
#         ac_bonus, attack_bonus, value_gp, source

ITEMS = [

    # ── Stat-setting wondrous items ─────────────────────────────────────────────
    {"name": "Gauntlets of Ogre Power",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "Your Strength score is 19 while you wear these gauntlets. No effect if your Strength is already 19 or higher.",
     "stat_set_str": 19, "value_gp": 8000},

    {"name": "Belt of Hill Giant Strength",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "Your Strength score is 21 while wearing this belt. No effect if already 21 or higher.",
     "stat_set_str": 21, "value_gp": 12000},

    {"name": "Belt of Stone Giant Strength",
     "category": "wondrous", "rarity": "rare", "requires_attunement": 1,
     "effect": "Your Strength score is 23 while wearing this belt. No effect if already 23 or higher.",
     "stat_set_str": 23, "value_gp": 18000},

    {"name": "Belt of Frost Giant Strength",
     "category": "wondrous", "rarity": "rare", "requires_attunement": 1,
     "effect": "Your Strength score is 23 while wearing this belt. No effect if already 23 or higher.",
     "stat_set_str": 23, "value_gp": 18000},

    {"name": "Belt of Fire Giant Strength",
     "category": "wondrous", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "Your Strength score is 25 while wearing this belt. No effect if already 25 or higher.",
     "stat_set_str": 25, "value_gp": 24000},

    {"name": "Belt of Cloud Giant Strength",
     "category": "wondrous", "rarity": "legendary", "requires_attunement": 1,
     "effect": "Your Strength score is 27 while wearing this belt. No effect if already 27 or higher.",
     "stat_set_str": 27, "value_gp": 40000},

    {"name": "Belt of Storm Giant Strength",
     "category": "wondrous", "rarity": "legendary", "requires_attunement": 1,
     "effect": "Your Strength score is 29 while wearing this belt. No effect if already 29 or higher.",
     "stat_set_str": 29, "value_gp": 50000},

    {"name": "Gloves of Dexterity",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "Your Dexterity score is 19 while wearing these gloves. No effect if already 19 or higher.",
     "stat_set_dex": 19, "value_gp": 8000},

    {"name": "Amulet of Health",
     "category": "wondrous", "rarity": "rare", "requires_attunement": 1,
     "effect": "Your Constitution score is 19 while wearing this amulet. No effect if already 19 or higher.",
     "stat_set_con": 19, "value_gp": 8000},

    {"name": "Headband of Intellect",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "Your Intelligence score is 19 while wearing this headband. No effect if already 19 or higher.",
     "stat_set_int": 19, "value_gp": 8000},

    {"name": "Periapt of Wisdom",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "Your Wisdom score is 19 while wearing this periapt. No effect if already 19 or higher.",
     "stat_set_wis": 19, "value_gp": 8000},

    {"name": "Cloak of Charisma",
     "category": "wondrous", "rarity": "rare", "requires_attunement": 1,
     "effect": "Your Charisma score is 18 while wearing this cloak. No effect if already 18 or higher.",
     "stat_set_cha": 18, "value_gp": 6000},

    # ── Stat-boosting tomes & manuals (permanent +2 to score and max) ───────────
    {"name": "Manual of Gainful Exercise",
     "category": "wondrous", "rarity": "very_rare",
     "effect": "Reading this manual over 48 hours increases your Strength score and maximum by 2. The manual then loses its magic for 100 years.",
     "stat_bonus_str": 2, "value_gp": 27500},

    {"name": "Manual of Quickness of Action",
     "category": "wondrous", "rarity": "very_rare",
     "effect": "Reading this manual over 48 hours increases your Dexterity score and maximum by 2. The manual then loses its magic for 100 years.",
     "stat_bonus_dex": 2, "value_gp": 27500},

    {"name": "Manual of Bodily Health",
     "category": "wondrous", "rarity": "very_rare",
     "effect": "Reading this manual over 48 hours increases your Constitution score and maximum by 2. The manual then loses its magic for 100 years.",
     "stat_bonus_con": 2, "value_gp": 27500},

    {"name": "Tome of Clear Thought",
     "category": "wondrous", "rarity": "very_rare",
     "effect": "Reading this tome over 48 hours increases your Intelligence score and maximum by 2. The tome then loses its magic for 100 years.",
     "stat_bonus_int": 2, "value_gp": 27500},

    {"name": "Tome of Understanding",
     "category": "wondrous", "rarity": "very_rare",
     "effect": "Reading this tome over 48 hours increases your Wisdom score and maximum by 2. The tome then loses its magic for 100 years.",
     "stat_bonus_wis": 2, "value_gp": 27500},

    {"name": "Tome of Leadership and Influence",
     "category": "wondrous", "rarity": "very_rare",
     "effect": "Reading this tome over 48 hours increases your Charisma score and maximum by 2. The tome then loses its magic for 100 years.",
     "stat_bonus_cha": 2, "value_gp": 27500},

    # ── AC-granting wondrous items ───────────────────────────────────────────────
    {"name": "Cloak of Protection",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "+1 bonus to AC and saving throws while wearing this cloak.",
     "ac_bonus": 1, "value_gp": 3500},

    {"name": "Ring of Protection",
     "category": "ring", "rarity": "rare", "requires_attunement": 1,
     "effect": "+1 bonus to AC and saving throws while wearing this ring.",
     "ac_bonus": 1, "value_gp": 3500},

    {"name": "Bracers of Defense",
     "category": "wondrous", "rarity": "rare", "requires_attunement": 1,
     "effect": "+2 bonus to AC while wearing these bracers, if not wearing armor or using a shield.",
     "ac_bonus": 2, "value_gp": 6000},

    {"name": "Ioun Stone of Protection",
     "category": "wondrous", "rarity": "rare", "requires_attunement": 1,
     "effect": "+1 bonus to AC while this ioun stone orbits your head.",
     "ac_bonus": 1, "value_gp": 1200},

    {"name": "Robe of the Archmagi",
     "category": "wondrous", "rarity": "legendary",
     "requires_attunement": 1, "attunement_by": "sorcerer, warlock, or wizard",
     "effect": "AC 15 + Dexterity modifier; advantage on saving throws vs. spells; spell save DC and spell attack bonus each increase by 2.",
     "ac_bonus": 0, "value_gp": 50000},

    # ── Magic weapons ──────────────────────────────────────────────────────────
    {"name": "+1 Weapon",
     "category": "weapon", "rarity": "uncommon",
     "effect": "+1 bonus to attack and damage rolls.",
     "attack_bonus": 1, "value_gp": 1000},

    {"name": "+2 Weapon",
     "category": "weapon", "rarity": "rare",
     "effect": "+2 bonus to attack and damage rolls.",
     "attack_bonus": 2, "value_gp": 4000},

    {"name": "+3 Weapon",
     "category": "weapon", "rarity": "very_rare",
     "effect": "+3 bonus to attack and damage rolls.",
     "attack_bonus": 3, "value_gp": 16000},

    {"name": "Berserker Axe",
     "category": "weapon", "rarity": "rare", "requires_attunement": 1,
     "effect": "+1 to attack and damage. When raging, gain +1 HP per Hit Die. Cursed: must attack nearest creature or DC 15 Wisdom save or attack nearest creature.",
     "attack_bonus": 1, "value_gp": 500},

    {"name": "Defender",
     "category": "weapon", "rarity": "legendary", "requires_attunement": 1,
     "effect": "+3 to attack and damage. Transfer any or all of the +3 bonus to AC instead until the start of your next turn.",
     "attack_bonus": 3, "value_gp": 50000},

    {"name": "Dragon Slayer",
     "category": "weapon", "rarity": "rare",
     "effect": "+1 to attack and damage. Against dragons, +3d6 extra damage and advantage on saving throws vs. dragon abilities.",
     "attack_bonus": 1, "value_gp": 8000},

    {"name": "Dwarven Thrower",
     "category": "weapon", "rarity": "very_rare",
     "requires_attunement": 1, "attunement_by": "dwarf",
     "effect": "+3 to attack and damage. Can be thrown (range 20/60). Returns after thrown. Deals extra 1d8 (or 2d8 vs. giants).",
     "attack_bonus": 3, "value_gp": 30000},

    {"name": "Flame Tongue",
     "category": "weapon", "rarity": "rare", "requires_attunement": 1,
     "effect": "Command word ignites blade: +2d6 fire damage, sheds bright light 40 ft and dim light 40 ft beyond.",
     "value_gp": 5000},

    {"name": "Frost Brand",
     "category": "weapon", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "+1d6 cold damage vs non-undead/non-construct. Resistance to fire. Extinguishes non-magical fires in 30 ft when drawn.",
     "value_gp": 12000},

    {"name": "Giant Slayer",
     "category": "weapon", "rarity": "rare",
     "effect": "+1 to attack and damage. Against giants: +2d6 extra damage and target must succeed DC 15 Strength save or fall prone.",
     "attack_bonus": 1, "value_gp": 9000},

    {"name": "Holy Avenger",
     "category": "weapon", "rarity": "legendary",
     "requires_attunement": 1, "attunement_by": "paladin",
     "effect": "+3 to attack and damage. +2d10 radiant vs. fiends and undead. Aura (10 ft): advantage on saves vs. spells and magic effects for you and friendly creatures.",
     "attack_bonus": 3, "value_gp": 50000},

    {"name": "Javelin of Lightning",
     "category": "weapon", "rarity": "uncommon",
     "effect": "Thrown as a lightning bolt (range 120 ft): 4d6 lightning, DC 13 Dex save for half. Becomes non-magical after use.",
     "value_gp": 1500},

    {"name": "Luck Blade",
     "category": "weapon", "rarity": "legendary", "requires_attunement": 1,
     "effect": "+1 to attack and damage. +1 to saving throws. 1–3 charges: reroll any d20 (use higher result). 1 charge: cast Wish (1/day).",
     "attack_bonus": 1, "value_gp": 60000},

    {"name": "Nine Lives Stealer",
     "category": "weapon", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "+2 to attack and damage. 1d8+1 charges: on a critical hit vs. creature with ≤100 HP, DC 15 Con save or die (soul stolen). Does not work vs. undead or constructs.",
     "attack_bonus": 2, "value_gp": 18000},

    {"name": "Oathbow",
     "category": "weapon", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "Swift Quiver: swear enmity against one creature. Advantage and +3d6 damage vs. sworn enemy. Disadvantage vs. others while enemy lives.",
     "value_gp": 18000},

    {"name": "Scimitar of Speed",
     "category": "weapon", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "+2 to attack and damage. Bonus action: make one attack with this scimitar.",
     "attack_bonus": 2, "value_gp": 18000},

    {"name": "Sun Blade",
     "category": "weapon", "rarity": "rare", "requires_attunement": 1,
     "effect": "+2 to attack and damage. Deals radiant instead of slashing. +1d8 radiant vs. undead. Sheds bright light 15 ft, dim 15 ft beyond. Finesse.",
     "attack_bonus": 2, "value_gp": 12000},

    {"name": "Sword of Life Stealing",
     "category": "weapon", "rarity": "rare", "requires_attunement": 1,
     "effect": "+3d6 necrotic on critical hit (non-construct, non-undead). Gain 10 temporary HP.",
     "value_gp": 8000},

    {"name": "Sword of Sharpness",
     "category": "weapon", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "+3d6 slashing on critical hit; critical on 20 severs a limb. Max damage dice on crits.",
     "value_gp": 18000},

    {"name": "Sword of Wounding",
     "category": "weapon", "rarity": "rare", "requires_attunement": 1,
     "effect": "+1 to attack and damage. Hit: target loses 1d4 HP at start of its next turn (no save; stacks; Medicine DC 15 to stop). No regen until short or long rest.",
     "attack_bonus": 1, "value_gp": 8000},

    {"name": "Vicious Weapon",
     "category": "weapon", "rarity": "rare",
     "effect": "+7 damage on a critical hit.",
     "value_gp": 350},

    {"name": "Vorpal Sword",
     "category": "weapon", "rarity": "legendary", "requires_attunement": 1,
     "effect": "+3 to attack and damage. Ignore slashing resistance/immunity. Critical hit on 20: decapitates (kills instantly unless no head or legendary resistance saves).",
     "attack_bonus": 3, "value_gp": 50000},

    {"name": "Weapon of Warning",
     "category": "weapon", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "You and companions within 30 ft cannot be surprised. Advantage on initiative while attuned.",
     "value_gp": 60000},

    {"name": "Dancing Sword",
     "category": "weapon", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "+1 to attack and damage. Bonus action: toss into air, floats and attacks independently (1 attack/round) for 1 minute. Returns after.",
     "attack_bonus": 1, "value_gp": 18000},

    {"name": "Dagger of Venom",
     "category": "weapon", "rarity": "rare",
     "effect": "+1 to attack and damage. Once/day: coat in poison for 1 minute; on hit DC 15 Con save or take 2d10 poison and poisoned for 1 minute.",
     "attack_bonus": 1, "value_gp": 2500},

    {"name": "Mace of Disruption",
     "category": "weapon", "rarity": "rare", "requires_attunement": 1,
     "effect": "Extra 2d6 radiant vs. fiends and undead. If target ≤25 HP after hit: DC 15 Wisdom save or destroyed (undead/fiend). Sheds bright light 20 ft, dim 20 ft beyond.",
     "value_gp": 8000},

    {"name": "Mace of Smiting",
     "category": "weapon", "rarity": "rare",
     "effect": "+1 to attack and damage (constructs: +3). Critical hit against a construct: extra 2d6 bludgeoning and DC 17 save or stunned 1 round.",
     "attack_bonus": 1, "value_gp": 8000},

    {"name": "Mace of Terror",
     "category": "weapon", "rarity": "rare", "requires_attunement": 1,
     "effect": "3 charges (recharge 1d3 dawn): use action, creatures within 30 ft DC 15 Wis save or frightened 1 minute.",
     "value_gp": 8000},

    {"name": "Trident of Fish Command",
     "category": "weapon", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "+1 to attack and damage (thrown). 3 charges: cast Dominate Beast (fish/amphibians only, DC 15). Recharge 1d3 at dawn.",
     "attack_bonus": 1, "value_gp": 800},

    # ── Magic armor ────────────────────────────────────────────────────────────
    {"name": "+1 Armor",
     "category": "armor", "rarity": "rare",
     "effect": "+1 bonus to AC. Available for any armor type.",
     "ac_bonus": 1, "value_gp": 1500},

    {"name": "+2 Armor",
     "category": "armor", "rarity": "very_rare",
     "effect": "+2 bonus to AC. Available for any armor type.",
     "ac_bonus": 2, "value_gp": 9000},

    {"name": "+3 Armor",
     "category": "armor", "rarity": "legendary",
     "effect": "+3 bonus to AC. Available for any armor type.",
     "ac_bonus": 3, "value_gp": 75000},

    {"name": "Adamantine Armor",
     "category": "armor", "rarity": "uncommon",
     "effect": "Any critical hit against you is treated as a normal hit instead. Available for medium and heavy armor.",
     "value_gp": 500},

    {"name": "Mithral Armor",
     "category": "armor", "rarity": "uncommon",
     "effect": "Mithral is light and flexible. Medium or heavy armor; no Strength requirement; does not impose disadvantage on Dexterity (Stealth) checks.",
     "value_gp": 1000},

    {"name": "Armor of Invulnerability",
     "category": "armor", "rarity": "legendary", "requires_attunement": 1,
     "effect": "Resistance to non-magical bludgeoning, piercing, and slashing damage. Action (once/day): immunity to non-magical damage for 10 minutes.",
     "value_gp": 50000},

    {"name": "Armor of Resistance",
     "category": "armor", "rarity": "rare", "requires_attunement": 1,
     "effect": "Resistance to one damage type (chosen when created: acid, cold, fire, force, lightning, necrotic, poison, psychic, radiant, or thunder).",
     "value_gp": 12000},

    {"name": "Armor of Vulnerability",
     "category": "armor", "rarity": "rare", "requires_attunement": 1,
     "effect": "Resistance to bludgeoning, piercing, or slashing (determined randomly). Cursed: vulnerability to the other two types.",
     "value_gp": 0},

    {"name": "Breastplate of Command",
     "category": "armor", "rarity": "rare", "requires_attunement": 1,
     "effect": "While wearing this armor, you can use an action to frighten creatures within 30 feet. AC 14 + Dex modifier (max 2). +1 bonus to AC.",
     "ac_bonus": 1, "value_gp": 8000},

    {"name": "Demon Armor",
     "category": "armor", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "+1 to AC. Unarmed strikes deal 1d8 slashing and count as magical. Cursed: cannot remove; disadvantage on attacks vs. demons.",
     "ac_bonus": 1, "value_gp": 20000},

    {"name": "Dragon Scale Mail",
     "category": "armor", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "+1 AC. Advantage on saves vs. the frightful presence of dragons. Resistance to the dragon type's damage. Once/day: know direction of nearest dragon within 30 miles.",
     "ac_bonus": 1, "value_gp": 20000},

    {"name": "Dwarven Plate",
     "category": "armor", "rarity": "very_rare",
     "effect": "AC 20. When a forced movement would move you, reduce movement by up to 10 feet.",
     "value_gp": 25000},

    {"name": "Efreeti Chain",
     "category": "armor", "rarity": "legendary", "requires_attunement": 1,
     "effect": "AC 16. Immunity to fire damage. You can speak and understand Ignan. At will: speak and understand all languages.",
     "value_gp": 60000},

    {"name": "Glamoured Studded Leather",
     "category": "armor", "rarity": "rare",
     "effect": "AC 12 + Dex. Bonus action: change the appearance of the armor to any other non-magical armor or normal clothing.",
     "value_gp": 2000},

    {"name": "Plate Armor of Etherealness",
     "category": "armor", "rarity": "legendary", "requires_attunement": 1,
     "effect": "AC 18. While wearing, can cast Etherealness at will (no spell slots). You become ethereal for up to 10 minutes (need not be consecutive).",
     "value_gp": 80000},

    # ── Rings ──────────────────────────────────────────────────────────────────
    {"name": "Ring of Animal Influence",
     "category": "ring", "rarity": "rare",
     "effect": "3 charges (recharge 1d3 dawn): cast Animal Friendship (DC 13), Fear (animals only, DC 13), or Speak with Animals.",
     "value_gp": 8000},

    {"name": "Ring of Djinni Summoning",
     "category": "ring", "rarity": "legendary", "requires_attunement": 1,
     "effect": "Once/day: summon a djinni that serves you for 1 hour. The djinni departs if killed or at end of 1 hour. Ring destroyed if djinni is killed.",
     "value_gp": 90000},

    {"name": "Ring of Evasion",
     "category": "ring", "rarity": "rare", "requires_attunement": 1,
     "effect": "3 charges (recharge 1d3 dawn): when you fail a Dex save, use your reaction to expend a charge and succeed instead.",
     "value_gp": 5000},

    {"name": "Ring of Feather Falling",
     "category": "ring", "rarity": "rare", "requires_attunement": 1,
     "effect": "When you fall while wearing this ring, you descend 60 ft per round and take no damage from falling.",
     "value_gp": 2000},

    {"name": "Ring of Free Action",
     "category": "ring", "rarity": "rare", "requires_attunement": 1,
     "effect": "Difficult terrain doesn't cost extra movement. Spells and effects can't paralyze you or reduce your speed to 0.",
     "value_gp": 8000},

    {"name": "Ring of Invisibility",
     "category": "ring", "rarity": "legendary", "requires_attunement": 1,
     "effect": "While wearing this ring, you can turn invisible as an action. Remain invisible until the ring is removed or you attack/cast a spell.",
     "value_gp": 50000},

    {"name": "Ring of Jumping",
     "category": "ring", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "Bonus action: cast Jump on yourself.",
     "value_gp": 2500},

    {"name": "Ring of Mind Shielding",
     "category": "ring", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "Immune to magic that allows other creatures to read thoughts, determine if lying, know alignment, or learn creature type. Telepathy only if you allow it.",
     "value_gp": 5000},

    {"name": "Ring of Regeneration",
     "category": "ring", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "Regain 1d6 HP every 10 minutes (only if at least 1 HP). Regrow lost limbs in 1d6+1 days if at least 1 HP. Does not function if you have 0 HP.",
     "value_gp": 30000},

    {"name": "Ring of Resistance",
     "category": "ring", "rarity": "rare", "requires_attunement": 1,
     "effect": "Resistance to one damage type (determined by stone in ring: acid, cold, fire, force, lightning, necrotic, poison, psychic, radiant, thunder).",
     "value_gp": 12000},

    {"name": "Ring of Shooting Stars",
     "category": "ring", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "Outdoors at night: cast Dancing Lights and Light cantrips. 6 charges: Faerie Fire (2), Ball Lightning (2), Shooting Stars (1–3). Recharge 1d6 at dawn.",
     "value_gp": 18000},

    {"name": "Ring of Spell Storing",
     "category": "ring", "rarity": "rare", "requires_attunement": 1,
     "effect": "Stores up to 5 levels of spells. Any creature can store spells. Attuned creature can cast stored spells using stored caster's stats.",
     "value_gp": 24000},

    {"name": "Ring of Spell Turning",
     "category": "ring", "rarity": "legendary", "requires_attunement": 1,
     "effect": "Advantage on saves vs. spells targeting only you. If save result is 20+ and spell is ≤7th level, reflect spell back at caster.",
     "value_gp": 50000},

    {"name": "Ring of Telekinesis",
     "category": "ring", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "Cast Telekinesis at will (no concentration).",
     "value_gp": 30000},

    {"name": "Ring of Three Wishes",
     "category": "ring", "rarity": "legendary",
     "effect": "3 charges: cast Wish. When all charges are used, the ring loses its magic.",
     "value_gp": 50000},

    {"name": "Ring of Warmth",
     "category": "ring", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "Resistance to cold damage. You and everything you wear/carry are unharmed by temperatures as low as −50°F.",
     "value_gp": 1000},

    {"name": "Ring of Water Walking",
     "category": "ring", "rarity": "uncommon",
     "effect": "Stand on and move across any liquid surface as if it were solid ground.",
     "value_gp": 1500},

    {"name": "Ring of X-ray Vision",
     "category": "ring", "rarity": "rare", "requires_attunement": 1,
     "effect": "Action: X-ray vision 30 ft through solid matter until start of next turn; blocked by 1 ft stone, 1 in. common metal, thin sheet lead, 3 ft wood/dirt. Con DC 15 or suffer exhaustion.",
     "value_gp": 6000},

    # ── Rods ───────────────────────────────────────────────────────────────────
    {"name": "Rod of Absorption",
     "category": "rod", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "Reaction: absorb a spell targeting only you, converting spell levels into charges. Up to 50 total levels; use charges to cast spells (max 5th). Useless once all 50 absorbed and expended.",
     "value_gp": 18000},

    {"name": "Rod of Alertness",
     "category": "rod", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "+1 to Perception. Advantage on initiative. Detect Evil and Good while held. Blindsight 60 ft for 10 minutes (1/day). Can cast Daylight (1/day) and Wall of Fire (1/day).",
     "value_gp": 20000},

    {"name": "Rod of Lordly Might",
     "category": "rod", "rarity": "legendary", "requires_attunement": 1,
     "effect": "Functions as +3 mace. 6 buttons: Flame Tongue, +4 AC (shield equivalent), Hold Monster, Paralysis, Fear, Drain life (2d4+2). Also extends to ladder, pole, or battering ram.",
     "attack_bonus": 3, "value_gp": 80000},

    {"name": "Rod of Rulership",
     "category": "rod", "rarity": "rare", "requires_attunement": 1,
     "effect": "Action (2/day recharge): creatures within 120 ft DC 15 Wisdom save or charmed for 8 hours (treat you as trusted leader). Ends if you/allies harm charmed creature.",
     "value_gp": 8000},

    {"name": "Rod of Security",
     "category": "rod", "rarity": "very_rare",
     "effect": "Action: transport up to 200 creatures to an extradimensional paradise for 200 days (divided by # of creatures). Creatures exit fully rested.",
     "value_gp": 30000},

    {"name": "Rod of the Pact Keeper +1",
     "category": "rod", "rarity": "uncommon",
     "requires_attunement": 1, "attunement_by": "warlock",
     "effect": "+1 to spell attack rolls and save DCs. Regain one warlock spell slot (1/day at dawn).",
     "value_gp": 6000},

    {"name": "Rod of the Pact Keeper +2",
     "category": "rod", "rarity": "rare",
     "requires_attunement": 1, "attunement_by": "warlock",
     "effect": "+2 to spell attack rolls and save DCs. Regain one warlock spell slot (1/day at dawn).",
     "value_gp": 20000},

    {"name": "Rod of the Pact Keeper +3",
     "category": "rod", "rarity": "very_rare",
     "requires_attunement": 1, "attunement_by": "warlock",
     "effect": "+3 to spell attack rolls and save DCs. Regain one warlock spell slot (1/day at dawn).",
     "value_gp": 50000},

    # ── Staves ─────────────────────────────────────────────────────────────────
    {"name": "Staff of Charming",
     "category": "staff", "rarity": "rare",
     "requires_attunement": 1, "attunement_by": "bard, cleric, druid, sorcerer, warlock, or wizard",
     "effect": "10 charges (recharge 1d6+4 dawn): Charm Person (1), Command (1), Comprehend Languages (1). Reaction: turn a failed Wis save into success and reflect charm back.",
     "value_gp": 16500},

    {"name": "Staff of Fire",
     "category": "staff", "rarity": "very_rare",
     "requires_attunement": 1, "attunement_by": "druid, sorcerer, warlock, or wizard",
     "effect": "10 charges (recharge 1d6+4 dawn): Burning Hands (1), Fireball (3), Wall of Fire (4). Resistance to fire damage.",
     "value_gp": 32000},

    {"name": "Staff of Frost",
     "category": "staff", "rarity": "very_rare",
     "requires_attunement": 1, "attunement_by": "druid, sorcerer, warlock, or wizard",
     "effect": "10 charges (recharge 1d6+4 dawn): Cone of Cold (5), Fog Cloud (1), Ice Storm (4), Wall of Ice (4). Resistance to cold.",
     "value_gp": 32000},

    {"name": "Staff of Healing",
     "category": "staff", "rarity": "rare",
     "requires_attunement": 1, "attunement_by": "bard, cleric, or druid",
     "effect": "10 charges (recharge 1d6+4 dawn): Cure Wounds (1–4 charges = 1d8 per charge), Lesser Restoration (2), Mass Cure Wounds (5).",
     "value_gp": 16500},

    {"name": "Staff of Power",
     "category": "staff", "rarity": "very_rare", "requires_attunement": 1,
     "attunement_by": "sorcerer, warlock, or wizard",
     "effect": "+2 to AC, saves, attack rolls. 20 charges: Cone of Cold (5), Fireball (5), Globe of Invulnerability (6), Hold Monster (5), Levitate (2), Magic Missile (1–7), Ray of Enfeeblement (1), Wall of Force (5). Staff also +2 quarterstaff.",
     "ac_bonus": 2, "attack_bonus": 2, "value_gp": 95335},

    {"name": "Staff of Striking",
     "category": "staff", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "+3 to attack and damage (functions as magic quarterstaff). 10 charges: expend 1–3 charges on a hit for +1d6 force per charge.",
     "attack_bonus": 3, "value_gp": 71960},

    {"name": "Staff of the Magi",
     "category": "staff", "rarity": "legendary",
     "requires_attunement": 1, "attunement_by": "sorcerer, warlock, or wizard",
     "effect": "+2 to spell attacks. Spell absorption (enemy spells). 50 charges: vast array of spells. Retributive Strike on destruction. Resistance to spell damage.",
     "attack_bonus": 2, "value_gp": 168000},

    {"name": "Staff of the Python",
     "category": "staff", "rarity": "uncommon",
     "requires_attunement": 1, "attunement_by": "cleric, druid, or warlock",
     "effect": "Action: transform into a giant constrictor snake that follows commands. Bonus action: revert. If snake reduced to 0 HP, staff destroyed.",
     "value_gp": 6000},

    {"name": "Staff of the Woodlands",
     "category": "staff", "rarity": "rare",
     "requires_attunement": 1, "attunement_by": "druid",
     "effect": "+2 attack/damage (quarterstaff). 10 charges: Animal Friendship (1), Awaken (5), Barkskin (2), Locate Animals/Plants (2), Speak with Animals (1), Speak with Plants (3), Wall of Thorns (6). Plant growth: plant staff to grow into tree.",
     "attack_bonus": 2, "value_gp": 16500},

    {"name": "Staff of Thunder and Lightning",
     "category": "staff", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "+2 attack/damage. Thunder (1/day): 2d6 thunder + deafened. Lightning (1/day): 9d6 lightning line. Thunder clap (1/day): 2d6 thunder all within 60 ft. Lightning strike (1/day): 10d6 lightning, disadvantage saves. Thunderbolt (1/week): 12d6 lightning in 10-ft-wide line, stuns.",
     "attack_bonus": 2, "value_gp": 50000},

    {"name": "Staff of Withering",
     "category": "staff", "rarity": "rare",
     "requires_attunement": 1, "attunement_by": "cleric, druid, or warlock",
     "effect": "3 charges (recharge 1d3 dawn): on hit, expend a charge to deal extra 2d10 necrotic; target DC 15 Con save or disadvantage on Strength checks/saves for 1 hour.",
     "value_gp": 8000},

    # ── Wands ──────────────────────────────────────────────────────────────────
    {"name": "Wand of Binding",
     "category": "wand", "rarity": "rare",
     "requires_attunement": 1, "attunement_by": "spellcaster",
     "effect": "7 charges (recharge 1d6+1 dawn): Hold Monster (5), Hold Person (2). Reaction: expend 2 charges when targeted to gain advantage on the escape roll.",
     "value_gp": 8000},

    {"name": "Wand of Enemy Detection",
     "category": "wand", "rarity": "rare", "requires_attunement": 1,
     "effect": "7 charges (recharge 1d6+1 dawn): action to expend a charge; know direction of nearest hostile creature within 60 ft for 1 minute.",
     "value_gp": 8000},

    {"name": "Wand of Fear",
     "category": "wand", "rarity": "rare", "requires_attunement": 1,
     "effect": "7 charges (recharge 1d6+1 dawn): Command (1), cone of fear 60 ft DC 15 Wisdom (2) or frighten 1 minute.",
     "value_gp": 8000},

    {"name": "Wand of Fireballs",
     "category": "wand", "rarity": "rare",
     "requires_attunement": 1, "attunement_by": "spellcaster",
     "effect": "7 charges (recharge 1d6+1 dawn): cast Fireball (DC 15, 3 charges; spend 1 extra charge per slot level above 3rd).",
     "value_gp": 8000},

    {"name": "Wand of Lightning Bolts",
     "category": "wand", "rarity": "rare",
     "requires_attunement": 1, "attunement_by": "spellcaster",
     "effect": "7 charges (recharge 1d6+1 dawn): cast Lightning Bolt (DC 15, 3 charges; spend 1 extra charge per slot level above 3rd).",
     "value_gp": 8000},

    {"name": "Wand of Magic Missiles",
     "category": "wand", "rarity": "uncommon",
     "effect": "7 charges (recharge 1d6+1 dawn): cast Magic Missile (1 charge per spell level 1–7).",
     "value_gp": 8000},

    {"name": "Wand of Paralysis",
     "category": "wand", "rarity": "rare",
     "requires_attunement": 1, "attunement_by": "spellcaster",
     "effect": "7 charges (recharge 1d6+1 dawn): action, creature within 60 ft DC 15 Con save or paralyzed 1 minute.",
     "value_gp": 8000},

    {"name": "Wand of Polymorph",
     "category": "wand", "rarity": "very_rare",
     "requires_attunement": 1, "attunement_by": "spellcaster",
     "effect": "7 charges (recharge 1d6+1 dawn): cast Polymorph (DC 15, 7 charges).",
     "value_gp": 18000},

    {"name": "Wand of Secrets",
     "category": "wand", "rarity": "uncommon",
     "effect": "3 charges (recharge 1d3 dawn): action within 30 ft of secret door or trap: learn its location.",
     "value_gp": 2000},

    {"name": "Wand of the War Mage +1",
     "category": "wand", "rarity": "uncommon",
     "requires_attunement": 1, "attunement_by": "spellcaster",
     "effect": "+1 to spell attack rolls. Ignore half cover for spell attacks.",
     "value_gp": 6000},

    {"name": "Wand of the War Mage +2",
     "category": "wand", "rarity": "rare",
     "requires_attunement": 1, "attunement_by": "spellcaster",
     "effect": "+2 to spell attack rolls. Ignore half cover for spell attacks.",
     "value_gp": 20000},

    {"name": "Wand of the War Mage +3",
     "category": "wand", "rarity": "very_rare",
     "requires_attunement": 1, "attunement_by": "spellcaster",
     "effect": "+3 to spell attack rolls. Ignore half cover for spell attacks.",
     "value_gp": 50000},

    {"name": "Wand of Web",
     "category": "wand", "rarity": "uncommon",
     "requires_attunement": 1, "attunement_by": "spellcaster",
     "effect": "7 charges (recharge 1d6+1 dawn): cast Web (2 charges, DC 15).",
     "value_gp": 8000},

    {"name": "Wand of Wonder",
     "category": "wand", "rarity": "rare",
     "requires_attunement": 1, "attunement_by": "spellcaster",
     "effect": "7 charges (recharge 1d6+1 dawn): action, expend a charge and roll d100 — random effect (table includes: Slow, Faerie Fire, Darkness, Stinking Cloud, confusion, lightning, butterflies, grass grows, etc.).",
     "value_gp": 8000},

    # ── Wondrous items — general ──────────────────────────────────────────────
    {"name": "Bag of Holding",
     "category": "wondrous", "rarity": "uncommon",
     "effect": "Interior 64 cubic feet (500 lb capacity). Weighs 15 lb regardless of contents. Retrieving an item: action. Breathing creatures suffocate after 10 minutes inside. If pierced/torn from outside, ruptures into Astral Plane.",
     "value_gp": 4000},

    {"name": "Bag of Tricks (Gray)",
     "category": "wondrous", "rarity": "uncommon",
     "effect": "3 charges (recharge 1d3 dawn): pull a fuzzy ball and throw it — becomes a random beast (weasel, giant rat, badger, boar, panther, giant badger, dire wolf, giant elk).",
     "value_gp": 300},

    {"name": "Bag of Tricks (Rust)",
     "category": "wondrous", "rarity": "uncommon",
     "effect": "3 charges (recharge 1d3 dawn): pull a fuzzy ball and throw it — becomes a random beast (rat, owl, mastiff, goat, giant goat, giant boar, lion, brown bear).",
     "value_gp": 300},

    {"name": "Bag of Tricks (Tan)",
     "category": "wondrous", "rarity": "uncommon",
     "effect": "3 charges (recharge 1d3 dawn): pull a fuzzy ball and throw it — becomes a random beast (jackal, ape, baboon, axe beak, black bear, giant weasel, giant hyena, tiger).",
     "value_gp": 300},

    {"name": "Boots of Elvenkind",
     "category": "wondrous", "rarity": "uncommon",
     "effect": "Your steps make no sound regardless of surface. Advantage on Dexterity (Stealth) checks that involve moving quietly.",
     "value_gp": 2500},

    {"name": "Boots of Speed",
     "category": "wondrous", "rarity": "rare", "requires_attunement": 1,
     "effect": "Bonus action: double your walking speed and opportunity attacks against you are made with disadvantage. Lasts until you use a bonus action to deactivate or until you remove the boots.",
     "value_gp": 8000},

    {"name": "Boots of Striding and Springing",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "Walking speed becomes 30 ft (if lower). Standing long jump up to 30 ft; standing high jump up to 15 ft.",
     "value_gp": 5000},

    {"name": "Boots of the Winterlands",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "Resistance to cold damage. Ignore difficult terrain created by ice or snow. Tolerate temperatures as low as −50°F without protection.",
     "value_gp": 3000},

    {"name": "Boots of Teleportation",
     "category": "wondrous", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "3 charges (recharge at dawn): cast Teleport. Charges are not regained if the boots lack all charges at dawn.",
     "value_gp": 18000},

    {"name": "Bracers of Archery",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "+2 damage rolls on longbow and shortbow attacks.",
     "value_gp": 1500},

    {"name": "Brooch of Shielding",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "Resistance to force damage. Immunity to Magic Missile spell.",
     "value_gp": 7500},

    {"name": "Carpet of Flying",
     "category": "wondrous", "rarity": "very_rare",
     "effect": "Magic carpet flies (command word). Sizes: 3×5 ft (200 lb, 80 ft speed), 4×6 ft (400 lb, 60 ft speed), 5×7 ft (600 lb, 40 ft speed), 6×9 ft (800 lb, 30 ft speed).",
     "value_gp": 30000},

    {"name": "Cloak of Displacement",
     "category": "wondrous", "rarity": "rare", "requires_attunement": 1,
     "effect": "Attackers have disadvantage on attack rolls against you. If you take damage, this property stops until the start of your next turn.",
     "value_gp": 60000},

    {"name": "Cloak of Elvenkind",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "While hood is up: Wisdom (Perception) checks to see you have disadvantage; Stealth checks advantage. Action to raise or lower hood.",
     "value_gp": 5000},

    {"name": "Cloak of the Bat",
     "category": "wondrous", "rarity": "rare", "requires_attunement": 1,
     "effect": "Advantage on Dexterity (Stealth) checks. Hang upside down. While in dim light or darkness: fly 40 ft speed (can't use arms) or wild shape into bat (druid only).",
     "value_gp": 6000},

    {"name": "Cloak of the Manta Ray",
     "category": "wondrous", "rarity": "uncommon",
     "effect": "Breathe underwater and swim speed 60 ft. The hood must be pulled up (covering the head and face) to activate.",
     "value_gp": 6000},

    {"name": "Crystal Ball",
     "category": "wondrous", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "Cast Scrying (DC 17) once per day. Variants: telepathy, true seeing, mind reading each add additional powers.",
     "value_gp": 50000},

    {"name": "Cube of Force",
     "category": "wondrous", "rarity": "rare", "requires_attunement": 1,
     "effect": "36 charges (recharge 1d20 dawn): press face to create a force cube around you. Various faces block different things (gas, living matter, non-living matter, spells, all).",
     "value_gp": 16000},

    {"name": "Decanter of Endless Water",
     "category": "wondrous", "rarity": "uncommon",
     "effect": "Three command words: still (1 gal/minute fresh water), stream (5 gal/minute), geyser (30 gal/round, 30 ft line, DC 13 Strength or knocked prone).",
     "value_gp": 135},

    {"name": "Deck of Many Things",
     "category": "wondrous", "rarity": "legendary",
     "effect": "Draw cards for random legendary effects: Vizier (answer 1 question), Sun (+6 ability score), Moon (1d3 wishes), Star (+2 ability score), Comet (solo defeat next foe for level), Fates (avoid any event), Throne (keep/hold), Key (magic sword), Knight (4th level fighter NPC), Gem (treasure), Talons (all magic destroyed), The Void (soul trapped), Flames (powerful devil enemy), Skull (death avatar), Ruin (wealth lost), Euryale (−2 saves), Rogue (close ally turns enemy), Balance (alignment changes), Jester (xp or draw), Fool (lose 10,000 xp and draw).",
     "value_gp": 0},

    {"name": "Dimensional Shackles",
     "category": "wondrous", "rarity": "rare",
     "effect": "Apply to incapacitated creature: the target is restrained and can't be teleported or moved to a different plane. Attacker must make DC 30 Strength check to remove. Reapply each dawn.",
     "value_gp": 15000},

    {"name": "Dust of Disappearance",
     "category": "wondrous", "rarity": "uncommon",
     "effect": "Sprinkle on a creature: that creature and everything it wears/carries becomes invisible for 2d4 minutes. Affected creatures are invisible to Blindsight.",
     "value_gp": 300},

    {"name": "Dust of Dryness",
     "category": "wondrous", "rarity": "uncommon",
     "effect": "Thrown into water (15-ft cube): absorbed into a marble. Marble thrown: releases 15-ft cube of water. Also instantly dries out water elementals (5d6 damage).",
     "value_gp": 120},

    {"name": "Dust of Sneezing and Choking",
     "category": "wondrous", "rarity": "uncommon",
     "effect": "Looks like Dust of Disappearance. Scattered: all within 30 ft DC 15 Con save or incapacitated and sufocating for 1 minute.",
     "value_gp": 0},

    {"name": "Elemental Gem",
     "category": "wondrous", "rarity": "uncommon",
     "effect": "Break gem: summon an elemental (blue sapphire=air, yellow diamond=earth, red corundum=fire, emerald=water). Serves for 1 hour.",
     "value_gp": 300},

    {"name": "Eyes of Charming",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "3 charges (recharge 1d3 dawn): cast Charm Person (DC 13).",
     "value_gp": 3000},

    {"name": "Eyes of Minute Seeing",
     "category": "wondrous", "rarity": "uncommon",
     "effect": "Darkvision 1 ft (see fine details, advantage on Investigation checks for objects within 1 ft).",
     "value_gp": 2500},

    {"name": "Eyes of the Eagle",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "Advantage on Wisdom (Perception) checks that rely on sight. Disadvantage on attacks and Perception in bright light unless shaded.",
     "value_gp": 2500},

    {"name": "Figurine of Wondrous Power (Bronze Griffon)",
     "category": "wondrous", "rarity": "rare",
     "effect": "Bronze statuette. When placed on ground and commanded, becomes a griffon for up to 6 hours (recharge 5 days). Can serve as a mount.",
     "value_gp": 10000},

    {"name": "Figurine of Wondrous Power (Ebony Fly)",
     "category": "wondrous", "rarity": "rare",
     "effect": "Carving of a horse fly. Becomes a giant fly (AC 11, HP 19) for up to 12 hours. Recharge 2 days. Can serve as mount (carrying capacity 450 lb).",
     "value_gp": 10000},

    {"name": "Figurine of Wondrous Power (Golden Lions)",
     "category": "wondrous", "rarity": "rare",
     "effect": "Pair of gold lion figurines. Each becomes a lion for up to 1 hour; recharge 1 week. Command each independently.",
     "value_gp": 10000},

    {"name": "Figurine of Wondrous Power (Ivory Goats)",
     "category": "wondrous", "rarity": "rare",
     "effect": "Three ivory goat figurines. Goat of Traveling (24 hours, recharge 1 week), Goat of Terror (3 hours, attack, recharge 15 days), Goat of Slaughter (3 hours, powerful combatant, one use).",
     "value_gp": 10000},

    {"name": "Figurine of Wondrous Power (Marble Elephant)",
     "category": "wondrous", "rarity": "rare",
     "effect": "Marble elephant. Becomes an elephant for up to 24 hours (recharge 1 week). Can serve as mount or beast of burden.",
     "value_gp": 10000},

    {"name": "Figurine of Wondrous Power (Obsidian Steed)",
     "category": "wondrous", "rarity": "very_rare",
     "effect": "Obsidian horse statuette. Becomes a nightmare (always hostile; 25% chance per use of being evil). Recharge 5 days.",
     "value_gp": 30000},

    {"name": "Figurine of Wondrous Power (Onyx Dog)",
     "category": "wondrous", "rarity": "rare",
     "effect": "Onyx dog statuette. Becomes a mastiff with Intelligence 8, speaks Common, and has Truesight 60 ft. Up to 6 hours (recharge 1 week).",
     "value_gp": 10000},

    {"name": "Figurine of Wondrous Power (Serpentine Owl)",
     "category": "wondrous", "rarity": "rare",
     "effect": "Serpentine owl statuette. Becomes a giant owl for up to 8 hours (recharge 2 days). Can telepathically communicate with you within 1 mile.",
     "value_gp": 10000},

    {"name": "Figurine of Wondrous Power (Silver Raven)",
     "category": "wondrous", "rarity": "uncommon",
     "effect": "Silver raven figurine. Becomes a raven for up to 12 hours (recharge 2 days). While raven: cast Animal Messenger through it.",
     "value_gp": 5000},

    {"name": "Folding Boat",
     "category": "wondrous", "rarity": "rare",
     "effect": "Box 12\" × 6\" × 2\". Three command words: (1) rowboat 10×4 ft with oars + oarlock (2) keelboat 24×8 ft (3) folds back to box. Furnishings appear/disappear with transformation.",
     "value_gp": 10000},

    {"name": "Gem of Brightness",
     "category": "wondrous", "rarity": "uncommon",
     "effect": "50 charges: (1) bright light 30 ft, (2) blinding beam 60 ft DC 15 Con (2 charges), (3) blinding burst all within 30 ft DC 15 Con (5 charges). Recharge none — single use pool.",
     "value_gp": 5000},

    {"name": "Gem of Seeing",
     "category": "wondrous", "rarity": "rare", "requires_attunement": 1,
     "effect": "3 charges (recharge 1d3 dawn): action, gain Truesight 120 ft for 10 minutes.",
     "value_gp": 32000},

    {"name": "Gloves of Missile Snaring",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "Reaction: when hit by a ranged weapon attack, reduce the damage by 1d10 + Dex modifier. If reduced to 0, catch the missile.",
     "value_gp": 6000},

    {"name": "Gloves of Swimming and Climbing",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "Climbing and swimming don't cost extra movement. +5 to Strength (Athletics) checks for climbing or swimming.",
     "value_gp": 2000},

    {"name": "Goggles of Night",
     "category": "wondrous", "rarity": "uncommon",
     "effect": "Darkvision 60 ft. If you already have darkvision, adds 60 ft to its range.",
     "value_gp": 150},

    {"name": "Handy Haversack",
     "category": "wondrous", "rarity": "rare",
     "effect": "Three compartments: two side pockets (20 lb, 2 cu ft each) and main section (80 lb, 8 cu ft). Weighs 5 lb. Desired items always come to hand. Breathing: 10 min suffocation.",
     "value_gp": 2000},

    {"name": "Helm of Brilliance",
     "category": "wondrous", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "1d10 diamonds, 2d10 rubies, 3d10 fire opals, 4d10 opals. Functions: Fireball (ruby, 10d6), Wall of Fire (fire opal), Daylight (opal), fire resistance (while gems remain), undead in 30 ft DC 15 Wis or flee. 1% chance/turn of shattering.",
     "value_gp": 50000},

    {"name": "Helm of Comprehending Languages",
     "category": "wondrous", "rarity": "uncommon",
     "effect": "Cast Comprehend Languages at will while wearing this helm.",
     "value_gp": 500},

    {"name": "Helm of Telepathy",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "Cast Detect Thoughts (DC 13) at will. While concentrating: communicate telepathically with creature whose mind you're reading (up to 1 mile).",
     "value_gp": 30000},

    {"name": "Helm of Teleportation",
     "category": "wondrous", "rarity": "rare", "requires_attunement": 1,
     "effect": "3 charges (recharge 1d3 dawn): cast Teleport.",
     "value_gp": 64000},

    {"name": "Horn of Blasting",
     "category": "wondrous", "rarity": "rare",
     "effect": "Action: 30-ft cone, 5d6 thunder, deafened 1 min, DC 15 Con. Structures/objects take 5d6. 20% chance on use: shatters and deals 10d6 to user.",
     "value_gp": 400},

    {"name": "Horn of Valhalla (Silver)",
     "category": "wondrous", "rarity": "rare",
     "effect": "Summon 2d4+2 berserker spirit warriors. They serve for 1 hour or until 0 HP. Recharge 7 days. Any class can use.",
     "value_gp": 11500},

    {"name": "Horn of Valhalla (Brass)",
     "category": "wondrous", "rarity": "rare",
     "effect": "Summon 3d4+3 berserkers. Recharge 7 days. Requires proficiency in martial weapons to use without suffering a geas.",
     "value_gp": 11500},

    {"name": "Horn of Valhalla (Bronze)",
     "category": "wondrous", "rarity": "very_rare",
     "effect": "Summon 4d4+4 berserkers. Recharge 7 days. Requires proficiency in medium armor.",
     "value_gp": 20000},

    {"name": "Horn of Valhalla (Iron)",
     "category": "wondrous", "rarity": "legendary",
     "effect": "Summon 5d4+5 berserkers. Recharge 7 days. Requires casting a spell of 1st level or higher within the past 24 hours.",
     "value_gp": 50000},

    {"name": "Instant Fortress",
     "category": "wondrous", "rarity": "rare",
     "effect": "Cube 1\" per side. Action: place on ground and speak command word. Expands to 20-ft square tower (60 ft tall, 5 ft thick walls). Drawbridge, arrow slits, 2 floors. AC 20, HP 500/floor. Shrinks to cube on command (must be empty).",
     "value_gp": 75000},

    {"name": "Iron Bands of Bilarro",
     "category": "wondrous", "rarity": "rare",
     "effect": "Rusty iron sphere. Action: throw at Large or smaller creature within 60 ft. Ranged attack (+9 to hit). Hit: bands erupt and restrain target. Target DC 20 Strength to break free. Recharge 1 dawn.",
     "value_gp": 5000},

    {"name": "Iron Flask",
     "category": "wondrous", "rarity": "legendary",
     "effect": "Trap a creature of any type (CR no limit) from another plane. DC 17 Charisma save. Contained creature can be released to serve for 1 hour. Flask can hold one creature at a time.",
     "value_gp": 30000},

    {"name": "Lantern of Revealing",
     "category": "wondrous", "rarity": "uncommon",
     "effect": "Burns for 6 hours on a flask of oil. Bright light 30 ft, dim 30 ft beyond. Reveals invisible creatures and objects within bright light.",
     "value_gp": 5000},

    {"name": "Luckstone",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "+1 to ability checks and saving throws.",
     "value_gp": 4200},

    {"name": "Mantle of Spell Resistance",
     "category": "wondrous", "rarity": "rare", "requires_attunement": 1,
     "effect": "Advantage on saving throws against spells.",
     "value_gp": 30000},

    {"name": "Medallion of Thoughts",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "3 charges (recharge 1d3 dawn): cast Detect Thoughts (DC 13).",
     "value_gp": 3000},

    {"name": "Mirror of Life Trapping",
     "category": "wondrous", "rarity": "very_rare",
     "effect": "Tall mirror. Hang facing a room: any creature within 30 ft that sees its reflection DC 15 Charisma save or trapped (up to 12 creatures). Break mirror: free all. Command word: speak to trapped creature.",
     "value_gp": 18000},

    {"name": "Necklace of Adaptation",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "Can breathe in any environment. Advantage on saves against harmful gases and vapors.",
     "value_gp": 1500},

    {"name": "Necklace of Fireballs",
     "category": "wondrous", "rarity": "rare",
     "effect": "1–9 beads (DM determines). Detach and throw (range 60 ft): explodes in 20-ft-radius Fireball. Multiple beads make bigger fireball. Each bead = +1d6.",
     "value_gp": 300},

    {"name": "Necklace of Prayer Beads",
     "category": "wondrous", "rarity": "rare",
     "requires_attunement": 1, "attunement_by": "cleric, druid, or paladin",
     "effect": "1d4+2 special beads: Bead of Blessing (Bless), Curing (2d4+2 HP), Favor (Greater Restoration), Smiting (Branding Smite), Summons (Planar Ally), Wind Walking (Wind Walk). Each bead 1/day.",
     "value_gp": 8000},

    {"name": "Periapt of Health",
     "category": "wondrous", "rarity": "uncommon",
     "effect": "Advantage on saves against disease. Immune to the poisoned condition.",
     "value_gp": 5000},

    {"name": "Periapt of Proof Against Poison",
     "category": "wondrous", "rarity": "rare",
     "effect": "Immunity to poison damage and the poisoned condition.",
     "value_gp": 5000},

    {"name": "Periapt of Wound Closure",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "Stable at 0 HP automatically. Death saving throw successes count double. When you roll a Hit Die during a short rest, double the HP regained.",
     "value_gp": 5000},

    {"name": "Portable Hole",
     "category": "wondrous", "rarity": "rare",
     "effect": "Cloth 6 ft in diameter. Unfold on solid surface: extradimensional hole 10 ft deep. Fold up: contents remain in pocket dimension. Interior 10 ft diameter × 10 ft deep. No air supply inside (suffocation 10 min).",
     "value_gp": 8000},

    {"name": "Quiver of Ehlonna",
     "category": "wondrous", "rarity": "uncommon",
     "effect": "Three compartments: 6 arrows/bolts, 18 arrows/bolts, or 1 long item (bow, staff, javelin). Always know which items are inside. Extradimensional storage.",
     "value_gp": 2000},

    {"name": "Robe of Eyes",
     "category": "wondrous", "rarity": "rare", "requires_attunement": 1,
     "effect": "See in all directions. Darkvision 120 ft. Advantage on Perception (sight). Can't be surprised. See invisible and ethereal creatures. Daylight blinds you: disadvantage on vision for 1 minute.",
     "value_gp": 30000},

    {"name": "Robe of Scintillating Colors",
     "category": "wondrous", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "3 charges (recharge 1d3 dawn): action, activate for 1 minute. Bright light 30 ft. Attackers DC 15 Con or blinded 1 round. Advantage on saves vs. spells.",
     "value_gp": 25000},

    {"name": "Robe of Stars",
     "category": "wondrous", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "+1 to saves. 6 charges: cast Magic Missile (1 charge each). Can enter astral plane (as Astral Projection, self only) 1/day.",
     "value_gp": 75000},

    {"name": "Robe of Useful Items",
     "category": "wondrous", "rarity": "uncommon",
     "effect": "Sewn on patches; each patch detaches and becomes the depicted item (dagger, bullseye lantern, mirror, 10-ft pole, rope 50 ft, sack, window, portable door, gem 100 gp, potion of healing, horses, pit 10-ft, rowboat, spell scroll, mastiffs, gold coins, ladder, bag 100 gp gems).",
     "value_gp": 700},

    {"name": "Rope of Climbing",
     "category": "wondrous", "rarity": "uncommon",
     "effect": "60-ft silk rope with 3000-lb limit. Command word: rope animates and ties itself to objects, knots itself, unties itself. Holds 3 climbing creatures simultaneously.",
     "value_gp": 2000},

    {"name": "Rope of Entanglement",
     "category": "wondrous", "rarity": "rare",
     "effect": "30-ft rope. Action: throw at creature within 35 ft. DC 15 Dex save or restrained. Strength DC 15 or Slash (AC 20, 20 HP, regrows/reties 1 dawn) to escape.",
     "value_gp": 4000},

    {"name": "Scarab of Protection",
     "category": "wondrous", "rarity": "legendary", "requires_attunement": 1,
     "effect": "Advantage on saves vs. spells. 12 charges: when you fail a death save, expend a charge to succeed instead. While charges remain, immune to necrotic and the frightened condition.",
     "value_gp": 50000},

    {"name": "Sending Stones",
     "category": "wondrous", "rarity": "uncommon",
     "effect": "Matched pair. Action: cast Sending to the creature holding the other stone. Only the holder of the other stone can reply. 1 message exchange per stone per day.",
     "value_gp": 3000},

    {"name": "Slippers of Spider Climbing",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "Climb speed 20 ft on difficult surfaces (including upside down), hands free. Does not function on slippery surfaces.",
     "value_gp": 5000},

    {"name": "Stone of Good Luck (Luckstone)",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "+1 bonus to ability checks and saving throws while the stone is on your person.",
     "value_gp": 4200},

    {"name": "Talisman of Pure Good",
     "category": "wondrous", "rarity": "legendary",
     "requires_attunement": 1, "attunement_by": "creature of good alignment",
     "effect": "7 charges: action, touch evil creature (cleric/paladin only) — fiend/undead must DC 20 Charisma save or destroyed. If non-good creature touches talisman: 6d6 radiant.",
     "value_gp": 50000},

    {"name": "Talisman of the Sphere",
     "category": "wondrous", "rarity": "legendary", "requires_attunement": 1,
     "effect": "Advantage on checks to control a Sphere of Annihilation. Roll 20 on check: move sphere 10 extra feet.",
     "value_gp": 100000},

    {"name": "Talisman of Ultimate Evil",
     "category": "wondrous", "rarity": "legendary",
     "requires_attunement": 1, "attunement_by": "creature of evil alignment",
     "effect": "6 charges: action, touch good creature — celestial must DC 20 Charisma save or destroyed. If non-evil creature touches it: 6d6 necrotic.",
     "value_gp": 50000},

    {"name": "Well of Many Worlds",
     "category": "wondrous", "rarity": "legendary",
     "effect": "Cloth 6 ft diameter. When thrown on ground, opens a two-way portal to a random location on another plane (DM's choice). Remains open until folded up. Refolds itself after 1 minute.",
     "value_gp": 50000},

    {"name": "Wind Fan",
     "category": "wondrous", "rarity": "uncommon",
     "effect": "Action: cast Gust of Wind (DC 13). Recharge: after use, 50% chance the fan is destroyed; otherwise recharges at dawn.",
     "value_gp": 500},

    {"name": "Winged Boots",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "Fly speed equal to walking speed. 4-hour flight battery (recharge 2 hours per 1 hour used). Minimum 1 hour charge needed to fly at all.",
     "value_gp": 8000},

    {"name": "Wings of Flying",
     "category": "wondrous", "rarity": "rare", "requires_attunement": 1,
     "effect": "Action: unfurl bat or bird wings. Flying speed 60 ft. Duration 1 hour (recharge 1 dawn). Wings retract when you stop flying or when duration ends.",
     "value_gp": 8000},

    {"name": "Ioun Stone of Agility",
     "category": "wondrous", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "Orbits your head. +2 to Dexterity score (max 20).",
     "stat_bonus_dex": 2, "value_gp": 10000},

    {"name": "Ioun Stone of Fortitude",
     "category": "wondrous", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "Orbits your head. +2 to Constitution score (max 20).",
     "stat_bonus_con": 2, "value_gp": 10000},

    {"name": "Ioun Stone of Insight",
     "category": "wondrous", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "Orbits your head. +2 to Intelligence score (max 20).",
     "stat_bonus_int": 2, "value_gp": 10000},

    {"name": "Ioun Stone of Intellect",
     "category": "wondrous", "rarity": "uncommon", "requires_attunement": 1,
     "effect": "Orbits your head. +1 to Intelligence score.",
     "stat_bonus_int": 1, "value_gp": 6000},

    {"name": "Ioun Stone of Leadership",
     "category": "wondrous", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "Orbits your head. +2 to Charisma score (max 20).",
     "stat_bonus_cha": 2, "value_gp": 10000},

    {"name": "Ioun Stone of Mastery",
     "category": "wondrous", "rarity": "legendary", "requires_attunement": 1,
     "effect": "Orbits your head. +1 to proficiency bonus.",
     "value_gp": 50000},

    {"name": "Ioun Stone of Protection",
     "category": "wondrous", "rarity": "rare", "requires_attunement": 1,
     "effect": "Orbits your head. +1 bonus to AC.",
     "ac_bonus": 1, "value_gp": 1200},

    {"name": "Ioun Stone of Strength",
     "category": "wondrous", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "Orbits your head. +2 to Strength score (max 20).",
     "stat_bonus_str": 2, "value_gp": 10000},

    {"name": "Ioun Stone of Sustenance",
     "category": "wondrous", "rarity": "rare", "requires_attunement": 1,
     "effect": "Orbits your head. You don't need to eat or drink.",
     "value_gp": 5000},

    {"name": "Ioun Stone of Vitality",
     "category": "wondrous", "rarity": "very_rare", "requires_attunement": 1,
     "effect": "Orbits your head. +2 to Wisdom score (max 20).",
     "stat_bonus_wis": 2, "value_gp": 10000},

    # ── Potions ────────────────────────────────────────────────────────────────
    {"name": "Potion of Healing",
     "category": "potion", "rarity": "common",
     "effect": "Regain 2d4+2 hit points. Drinking or administering takes an action.",
     "value_gp": 50},

    {"name": "Potion of Greater Healing",
     "category": "potion", "rarity": "uncommon",
     "effect": "Regain 4d4+4 hit points.",
     "value_gp": 150},

    {"name": "Potion of Superior Healing",
     "category": "potion", "rarity": "rare",
     "effect": "Regain 8d4+8 hit points.",
     "value_gp": 500},

    {"name": "Potion of Supreme Healing",
     "category": "potion", "rarity": "very_rare",
     "effect": "Regain 10d4+20 hit points.",
     "value_gp": 1350},

    {"name": "Potion of Animal Friendship",
     "category": "potion", "rarity": "uncommon",
     "effect": "After drinking, cast Animal Friendship (DC 13) at will for 1 hour.",
     "value_gp": 200},

    {"name": "Potion of Clairvoyance",
     "category": "potion", "rarity": "rare",
     "effect": "Gain the effect of the Clairvoyance spell for 1 hour.",
     "value_gp": 960},

    {"name": "Potion of Climbing",
     "category": "potion", "rarity": "common",
     "effect": "Climb speed equal to walking speed for 1 hour. Advantage on Strength (Athletics) checks for climbing.",
     "value_gp": 75},

    {"name": "Potion of Diminution",
     "category": "potion", "rarity": "rare",
     "effect": "Reduce as if under Enlarge/Reduce (reduce option) for 1d4 hours. No concentration.",
     "value_gp": 270},

    {"name": "Potion of Fire Breath",
     "category": "potion", "rarity": "uncommon",
     "effect": "Up to 3 times in 1 hour: bonus action, breathe fire in 30-ft cone (4d6 fire, DC 13 Dex for half).",
     "value_gp": 150},

    {"name": "Potion of Flying",
     "category": "potion", "rarity": "very_rare",
     "effect": "Fly speed equal to walking speed for 1 hour. No concentration.",
     "value_gp": 500},

    {"name": "Potion of Gaseous Form",
     "category": "potion", "rarity": "rare",
     "effect": "Gaseous Form (self only) for up to 1 hour. No concentration.",
     "value_gp": 300},

    {"name": "Potion of Giant Strength (Hill)",
     "category": "potion", "rarity": "uncommon",
     "effect": "STR becomes 21 for 1 hour (no effect if already 21+). No concentration.",
     "stat_set_str": 21, "value_gp": 200},

    {"name": "Potion of Giant Strength (Stone/Frost)",
     "category": "potion", "rarity": "rare",
     "effect": "STR becomes 23 for 1 hour (no effect if already 23+). No concentration.",
     "stat_set_str": 23, "value_gp": 800},

    {"name": "Potion of Giant Strength (Fire)",
     "category": "potion", "rarity": "rare",
     "effect": "STR becomes 25 for 1 hour (no effect if already 25+). No concentration.",
     "stat_set_str": 25, "value_gp": 800},

    {"name": "Potion of Giant Strength (Cloud)",
     "category": "potion", "rarity": "very_rare",
     "effect": "STR becomes 27 for 1 hour (no effect if already 27+). No concentration.",
     "stat_set_str": 27, "value_gp": 1500},

    {"name": "Potion of Giant Strength (Storm)",
     "category": "potion", "rarity": "legendary",
     "effect": "STR becomes 29 for 1 hour (no effect if already 29+). No concentration.",
     "stat_set_str": 29, "value_gp": 5000},

    {"name": "Potion of Growth",
     "category": "potion", "rarity": "uncommon",
     "effect": "Enlarge as per Enlarge/Reduce (enlarge option) for 1d4 hours. No concentration.",
     "value_gp": 270},

    {"name": "Potion of Heroism",
     "category": "potion", "rarity": "rare",
     "effect": "Blessed (as per the Bless spell) and gain 10 temporary HP for 1 hour. No concentration.",
     "value_gp": 180},

    {"name": "Potion of Invisibility",
     "category": "potion", "rarity": "very_rare",
     "effect": "Invisible for 1 hour. Ends early if you attack or cast a spell.",
     "value_gp": 180},

    {"name": "Potion of Mind Reading",
     "category": "potion", "rarity": "rare",
     "effect": "Cast Detect Thoughts (DC 13) for 1 hour. No concentration.",
     "value_gp": 180},

    {"name": "Potion of Poison",
     "category": "potion", "rarity": "uncommon",
     "effect": "Appears as Potion of Healing. Poisoned on drinking: 3d6 poison damage immediately, DC 13 Con save or 3d6 poison and poisoned for 1 hour.",
     "value_gp": 100},

    {"name": "Potion of Resistance",
     "category": "potion", "rarity": "uncommon",
     "effect": "Resistance to one damage type (DM chooses or roll randomly) for 1 hour.",
     "value_gp": 300},

    {"name": "Potion of Speed",
     "category": "potion", "rarity": "very_rare",
     "effect": "Haste (self only) for 1 minute. No concentration.",
     "value_gp": 400},

    {"name": "Potion of Water Breathing",
     "category": "potion", "rarity": "uncommon",
     "effect": "Breathe underwater for 1 hour.",
     "value_gp": 180},

    # ── Scrolls ────────────────────────────────────────────────────────────────
    {"name": "Spell Scroll (Cantrip)",
     "category": "scroll", "rarity": "common",
     "effect": "A cantrip spell is written on the scroll. Spellcasters of appropriate class can cast it; others DC 10 Arcana check. Scroll destroyed on use.",
     "value_gp": 25},

    {"name": "Spell Scroll (1st Level)",
     "category": "scroll", "rarity": "common",
     "effect": "A 1st-level spell. Spell save DC 13, +5 attack bonus. Scroll destroyed on use.",
     "value_gp": 75},

    {"name": "Spell Scroll (2nd Level)",
     "category": "scroll", "rarity": "uncommon",
     "effect": "A 2nd-level spell. Spell save DC 13, +5 attack bonus.",
     "value_gp": 150},

    {"name": "Spell Scroll (3rd Level)",
     "category": "scroll", "rarity": "uncommon",
     "effect": "A 3rd-level spell. Spell save DC 15, +7 attack bonus.",
     "value_gp": 300},

    {"name": "Spell Scroll (4th Level)",
     "category": "scroll", "rarity": "rare",
     "effect": "A 4th-level spell. Spell save DC 15, +7 attack bonus.",
     "value_gp": 500},

    {"name": "Spell Scroll (5th Level)",
     "category": "scroll", "rarity": "rare",
     "effect": "A 5th-level spell. Spell save DC 17, +9 attack bonus.",
     "value_gp": 1000},

    {"name": "Spell Scroll (6th Level)",
     "category": "scroll", "rarity": "very_rare",
     "effect": "A 6th-level spell. Spell save DC 17, +9 attack bonus.",
     "value_gp": 2000},

    {"name": "Spell Scroll (7th Level)",
     "category": "scroll", "rarity": "very_rare",
     "effect": "A 7th-level spell. Spell save DC 18, +10 attack bonus.",
     "value_gp": 5000},

    {"name": "Spell Scroll (8th Level)",
     "category": "scroll", "rarity": "very_rare",
     "effect": "An 8th-level spell. Spell save DC 18, +10 attack bonus.",
     "value_gp": 10000},

    {"name": "Spell Scroll (9th Level)",
     "category": "scroll", "rarity": "legendary",
     "effect": "A 9th-level spell. Spell save DC 19, +11 attack bonus.",
     "value_gp": 50000},

    {"name": "Scroll of Protection",
     "category": "scroll", "rarity": "rare",
     "effect": "Read as action: protected from one creature type (aberrations, beasts, celestials, elementals, fey, fiends, or undead). Creatures of that type within 5 ft: DC 15 Charisma or can't enter your space for 5 minutes.",
     "value_gp": 500},
]


def seed():
    init_db()
    seeded = 0
    for item in ITEMS:
        # Ensure all integer fields default to 0
        for field in ("stat_set_str","stat_set_dex","stat_set_con","stat_set_int","stat_set_wis","stat_set_cha",
                      "stat_bonus_str","stat_bonus_dex","stat_bonus_con","stat_bonus_int","stat_bonus_wis","stat_bonus_cha",
                      "ac_bonus","attack_bonus","value_gp"):
            item.setdefault(field, 0)
        item.setdefault("requires_attunement", 0)
        item.setdefault("attunement_by", "")
        item.setdefault("source", "DMG/SRD")
        upsert_magic_item(item)
        seeded += 1

    total = count_magic_items()
    print(f"Seeded {seeded} items ({total} total in DB).")


if __name__ == "__main__":
    seed()
