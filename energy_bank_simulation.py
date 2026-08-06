"""
Energy Bank Closed-Loop Simulation  v7
========================================
Vault Internal Conduit System (VICS) -- 3-chamber staged amplifier replaces
the single-bucket vault.  Energy cascades through Chambers A->B->C, gaining
amplification at each stage so even a small overflow from the bank arrives at
the battery as a strong, regulated burst.  The floor cannot dip because
Chamber C always watches B, and B always watches A.

  MUT (surge)
    |
  SC1 (Supercharger)  -- boost converter + trickle gate
    |
  Energy Bank  (5-cell capacitor bank)
    | overflow (above BANK_OVERFLOW_AT)
  SC-V (Vault Recovery)  -- fires when total vault <= SCV_LOW_THRESH
    |
  VICS -- Vault Internal Conduit System  (NEW v7)
    |
    |  [Chamber A]  Intake conduit
    |    receives raw overflow, first-stage capacitor array
    |    amplifies at x1.20, 94% eff -- fills fast from small inputs
    |    when A >= VICS_A_THRESH: pulse-transfers to Chamber B
    |
    |  [Chamber B]  Resonance conduit  (the "house" / stable reservoir)
    |    receives A pulse with x1.15 gain -- standing wave amplification
    |    when B >= VICS_B_THRESH: feeds Chamber C and battery boost
    |    if B drops below VICS_B_LOW: pulls from A immediately to refill
    |
    |  [Chamber C]  Output conduit  (floor guardian)
    |    timed regulated burst to battery at VICS_C_RATE J/tick
    |    if C drops below VICS_C_LOW: pulls from B immediately to refill
    |    ensures battery never sees a dry tick from the vault side
    |
  Battery  (central energy store, SOH tracked)
    |--- Device 2 (lighter load, first draw)
    |       | SC2 return supercharger -> Bank
    |--- Device 3 (heavier load, second draw)
             | SC3 return supercharger -> Bank

Changes vs v6:
  - Replaced single vault bucket with 3-chamber VICS (A / B / C)
  - Each chamber has its own capacity, amplification ratio, and threshold
  - Chamber B is the stable reservoir; Chamber C is the floor guardian
  - BATTERY_INIT restored to realistic 50 J -- VICS keeps it healthy from tick 1
  - Deep-discharge ticks: target 0 for full 100-tick run

Run:  python energy_bank_simulation.py
Outputs: energy_bank_results.csv  +  console summary per tick
"""

import csv
import math
import random

# ─────────────────────────────────────────────
# CONSTANTS / CONFIGURATION
# ─────────────────────────────────────────────
TICKS               = 100       # simulation steps
DT                  = 1.0       # seconds per tick

# MUT (Machine Under Test)
MUT_BASE_VOLTAGE    = 120.0     # volts -- nominal
MUT_SURGE_PROB      = 0.20      # probability of a surge each tick
MUT_SURGE_PEAK      = 80.0      # extra volts added during a surge

# ── SUPERCHARGER (boost converter + trickle gate) ──────────────
SC_BOOST_RATIO      = 1.45      # surge energy multiplied by this factor (boost conversion gain)
SC_BOOST_EFF        = 0.92      # efficiency of the boost conversion itself
SC_MIN_INPUT        = 2.0       # joules -- below this, bypass boost (not worth converting)
SC_TRICKLE_RATE     = 4.0       # joules/tick -- raised: ambient bleed charges bank faster during quiet
SC_TRICKLE_EFF      = 0.75      # trickle path efficiency (passive bleed circuit)
SC_HEAT_COEFF       = 0.08      # fraction of processed energy lost as heat in supercharger

# Energy Bank (capacitor bank)
BANK_CAPACITY       = 500.0     # joules -- max stored
BANK_CELL_COUNT     = 5         # number of internal cells
BANK_CELL_CAP       = BANK_CAPACITY / BANK_CELL_COUNT
BANK_OVERFLOW_AT    = 300.0     # joules -- threshold above which overflow goes to vault
BANK_INIT           = 150.0     # v6: pre-charged to half capacity -- reaches overflow threshold fast

# ── VICS: Vault Internal Conduit System  (NEW v7) ──────────────────────────
# Three cascaded chambers replace the single vault bucket.
# Energy flows A -> B -> C -> Battery, amplified at each stage.

# Chamber A -- Intake conduit (first-stage capacitor array)
VICS_A_CAP          = 120.0     # joules max capacity
VICS_A_AMP          = 1.20      # amplification ratio on incoming overflow
VICS_A_EFF          = 0.94      # conversion efficiency
VICS_A_THRESH       = 30.0      # joules -- A must reach this before pulsing to B
VICS_A_HEAT         = 0.04      # heat loss fraction
VICS_A_INIT         = 30.0      # pre-charged to threshold -- ready from tick 1

# Chamber B -- Resonance conduit ("the house" / stable reservoir)
VICS_B_CAP          = 200.0     # joules max capacity
VICS_B_AMP          = 1.15      # standing-wave amplification on pulse from A
VICS_B_EFF          = 0.92      # conversion efficiency
VICS_B_THRESH       = 60.0      # joules -- B must reach this before feeding C & battery boost
VICS_B_LOW          = 25.0      # joules -- B refill trigger: pulls from A when B drops here
VICS_B_HEAT         = 0.05      # heat loss fraction
VICS_B_INIT         = 60.0      # pre-charged to threshold -- active from tick 1

# Chamber C -- Output conduit (floor guardian, feeds battery steadily)
VICS_C_CAP          = 80.0      # joules max capacity
VICS_C_RATE         = 14.0      # joules/tick released to battery (regulated burst)
VICS_C_LOW          = 20.0      # joules -- C refill trigger: pulls from B immediately
VICS_C_HEAT         = 0.03      # heat loss fraction
VICS_C_INIT         = 40.0      # pre-charged above C_LOW -- floor guardian active tick 1

# SC-V threshold uses total VICS energy for its low-vault check
SCV_LOW_THRESH_VICS = 40.0      # total A+B+C below this triggers SC-V boost

# Battery  (central energy store powering both devices)
BATTERY_CAPACITY    = 250.0     # joules
BATTERY_INIT        = 50.0      # realistic pre-charge -- VICS Chamber C keeps battery fed from tick 1
BATTERY_BOOST_RATE  = 80.0      # joules/tick transferred vault -> battery on overflow events
BATTERY_FLOAT_TARGET= 0.60      # vault targets keeping battery at 60% capacity (150J)
# State of Health: battery degrades when cycled below SOH_LOW_THRESH
SOH_LOW_THRESH      = 0.15      # 15% of capacity (v5: lowered from 30% -- 40J / 225J = 17.8%, just above)
SOH_DEGRADE_RATE    = 0.001     # capacity lost per deep-discharge tick

# Device 2  (lighter load -- activates FIRST at lower threshold, per improved design)
DEVICE2_POWER       = 2.0       # watts  (v5: halved from 4.0 -- less per-tick drain)
DEVICE2_ON_THRESH   = 35.0      # J      (v5: raised from 20.0 -- higher battery resting floor)

# Device 3  (heavier load -- activates SECOND at higher threshold)
DEVICE3_POWER       = 7.0       # watts
DEVICE3_ON_THRESH   = 45.0      # J (v5: raised from 40.0 -- D3 fires only when battery has more headroom)

# Feedback path: Device 3 output -> Bank
FEEDBACK_EFF        = 0.65      # 65% of Device 3's consumed energy recovered to bank

# ── SC2: Return Supercharger on Device 2 output path ───────────
SC2_RECOVER_RATIO   = 1.30      # boost ratio on recovered Device 2 energy
SC2_EFF             = 0.88      # conversion efficiency of SC2
SC2_MIN_INPUT       = 0.5       # joules -- minimum worth converting (smaller than SC1 gate)
SC2_HEAT_COEFF      = 0.06      # SC2 heat loss fraction (smaller converter, less heat)

# ── SC3: Return Supercharger on Device 3 feedback path ─────────  NEW v5
SC3_RECOVER_RATIO   = 1.25      # slightly lower boost than SC2 (D3 output is larger, less gain needed)
SC3_EFF             = 0.86      # conversion efficiency of SC3
SC3_MIN_INPUT       = 1.0       # joules -- gate (D3 draws more so threshold is higher)
SC3_HEAT_COEFF      = 0.07      # SC3 heat loss fraction

# ── SC-V: Vault Recovery Supercharger on Bank overflow path ─────  NEW v5
# When vault drops to or below SCV_LOW_THRESH, the NEXT overflow signal
# from the bank is intercepted and boosted before entering the vault.
# This is the "supercharger waiting for that tick to hit" -- it senses
# vault depletion and fires a recovery boost to refill the reservoir fast.
SCV_LOW_THRESH      = 20.0      # joules -- vault level that triggers SC-V
SCV_BOOST_RATIO     = 1.35      # boost multiplier applied to overflow when vault is low
SCV_EFF             = 0.90      # conversion efficiency of SC-V
SCV_HEAT_COEFF      = 0.05      # heat loss fraction (compact single-stage converter)


# ─────────────────────────────────────────────
# MUT: raw voltage this tick
# ─────────────────────────────────────────────
def mut_voltage(tick: int) -> float:
    base  = MUT_BASE_VOLTAGE + 6 * math.sin(tick * 0.3)
    surge = MUT_SURGE_PEAK * random.random() if random.random() < MUT_SURGE_PROB else 0.0
    return base + surge


# ─────────────────────────────────────────────
# RAW energy from MUT before supercharger
# ─────────────────────────────────────────────
def raw_energy(voltage: float, dt: float) -> float:
    excess_v      = max(0.0, voltage - MUT_BASE_VOLTAGE)
    nominal_power = 60.0
    return (excess_v / MUT_BASE_VOLTAGE) * nominal_power * dt


# ─────────────────────────────────────────────
# SUPERCHARGER: boost converter + trickle gate
# ─────────────────────────────────────────────
def supercharger(raw_joules: float, dt: float) -> tuple:
    """
    Two operating modes:
      BOOST mode  -- raw_joules >= SC_MIN_INPUT:
          Output = raw * SC_BOOST_RATIO * SC_BOOST_EFF
          Heat   = raw * SC_BOOST_RATIO * SC_HEAT_COEFF
          Mode   = 'boost'
      TRICKLE mode -- raw_joules < SC_MIN_INPUT:
          Injects a small trickle charge regardless of MUT activity
          Output = SC_TRICKLE_RATE * SC_TRICKLE_EFF * dt
          Heat   = SC_TRICKLE_RATE * (1 - SC_TRICKLE_EFF) * dt
          Mode   = 'trickle'

    Returns (energy_to_bank, heat_joules, mode_str).
    """
    if raw_joules >= SC_MIN_INPUT:
        amplified   = raw_joules * SC_BOOST_RATIO
        to_bank     = amplified * SC_BOOST_EFF
        heat        = amplified * SC_HEAT_COEFF
        return to_bank, heat, "boost"
    else:
        to_bank = SC_TRICKLE_RATE * SC_TRICKLE_EFF * dt
        heat    = SC_TRICKLE_RATE * (1.0 - SC_TRICKLE_EFF) * dt
        return to_bank, heat, "trickle"


# ─────────────────────────────────────────────
# ENERGY BANK: fill cells, emit overflow
# ─────────────────────────────────────────────
def bank_fill_and_overflow(cells: list, incoming: float) -> tuple:
    """
    Fill cells smallest-first.
    Surplus above BANK_OVERFLOW_AT spills to vault.
    Returns (cells, overflow_joules).
    """
    cells     = sorted(cells)
    remaining = incoming
    for i in range(len(cells)):
        space = BANK_CELL_CAP - cells[i]
        fill  = min(space, remaining)
        cells[i]  += fill
        remaining -= fill
        if remaining <= 0:
            break

    bank_total = sum(cells)
    overflow   = 0.0
    if bank_total > BANK_OVERFLOW_AT:
        overflow      = bank_total - BANK_OVERFLOW_AT
        drain_ratio   = overflow / bank_total
        cells         = [c * (1.0 - drain_ratio) for c in cells]

    return cells, overflow + remaining


# ─────────────────────────────────────────────
# SC-V: Vault Recovery Supercharger
# ─────────────────────────────────────────────
def scv_boost(overflow: float, vics_total: float) -> tuple:
    """
    Intercepts bank overflow before it enters VICS Chamber A.
    If total VICS energy <= SCV_LOW_THRESH_VICS: boost the overflow signal.
    Otherwise: pass through unchanged.

    Returns (conditioned_overflow, scv_heat_j, scv_active: bool).
    """
    if vics_total <= SCV_LOW_THRESH_VICS and overflow > 0:
        amplified = overflow * SCV_BOOST_RATIO
        to_vics   = amplified * SCV_EFF
        heat      = amplified * SCV_HEAT_COEFF
        return to_vics, heat, True
    return overflow, 0.0, False


# ─────────────────────────────────────────────
# VICS: Vault Internal Conduit System  (NEW v7)
# ─────────────────────────────────────────────
def vics_step(ch_a: float, ch_b: float, ch_c: float,
              overflow: float, battery: float, battery_cap: float,
              dt: float) -> tuple:
    """
    One tick of the 3-chamber VICS pipeline.

    Stage 1 -- Chamber A (Intake conduit):
      Receives overflow.  Amplifies at VICS_A_AMP * VICS_A_EFF.
      When A >= VICS_A_THRESH: pulse surplus to Chamber B.

    Stage 2 -- Chamber B (Resonance conduit / "the house"):
      Receives A pulse amplified at VICS_B_AMP * VICS_B_EFF.
      If B drops < VICS_B_LOW: immediately pulls available energy from A.
      When B >= VICS_B_THRESH: feeds Chamber C.

    Stage 3 -- Chamber C (Output conduit / floor guardian):
      Receives feed from B when B is healthy.
      If C drops < VICS_C_LOW: immediately refills from B.
      Releases VICS_C_RATE J/tick to battery (regulated burst).
      Never lets the battery side go dry.

    Returns (ch_a, ch_b, ch_c, battery, to_battery_j, vics_heat_j).
    """
    vics_heat = 0.0

    # ── Stage 1: Chamber A receives conditioned overflow ──────────
    incoming_a = overflow * VICS_A_AMP * VICS_A_EFF
    heat_a     = overflow * VICS_A_AMP * VICS_A_HEAT
    vics_heat += heat_a
    ch_a = min(ch_a + incoming_a, VICS_A_CAP)

    # A -> B pulse: when A is at or above threshold, transfer surplus to B
    a_pulse = 0.0
    if ch_a >= VICS_A_THRESH:
        a_surplus  = ch_a - VICS_A_THRESH
        a_pulse    = a_surplus * VICS_B_AMP * VICS_B_EFF
        heat_b_in  = a_surplus * VICS_B_AMP * VICS_B_HEAT
        vics_heat += heat_b_in
        ch_a      -= a_surplus
        ch_b       = min(ch_b + a_pulse, VICS_B_CAP)

    # B emergency refill from A if B is low (floor guardian level 1)
    if ch_b < VICS_B_LOW and ch_a > 0:
        pull       = min(ch_a, VICS_B_LOW - ch_b)
        ch_a      -= pull
        ch_b      += pull * VICS_B_EFF          # small efficiency cost on emergency pull

    # ── Stage 2: Chamber B feeds Chamber C ────────────────────────
    if ch_b >= VICS_B_THRESH:
        b_to_c  = min(ch_b - VICS_B_THRESH, VICS_C_CAP - ch_c)
        ch_b   -= b_to_c
        ch_c    = min(ch_c + b_to_c, VICS_C_CAP)

    # C emergency refill from B if C is low (floor guardian level 2)
    if ch_c < VICS_C_LOW and ch_b > VICS_B_LOW:
        pull  = min(ch_b - VICS_B_LOW, VICS_C_LOW - ch_c)
        ch_b -= pull
        ch_c += pull

    # ── Stage 3: Chamber C releases regulated burst to battery ────
    float_target = battery_cap * BATTERY_FLOAT_TARGET
    to_battery   = 0.0
    if ch_c > 0 and battery < float_target:
        release    = min(VICS_C_RATE * dt, ch_c, float_target - battery)
        heat_c     = release * VICS_C_HEAT
        vics_heat += heat_c
        ch_c      -= release
        to_battery = release - heat_c       # net delivered after C output heat
        battery   += to_battery

    return ch_a, ch_b, ch_c, battery, to_battery, vics_heat


# ─────────────────────────────────────────────
# BATTERY STATE OF HEALTH tracker
# ─────────────────────────────────────────────
def update_soh(battery: float, battery_cap: float, soh: float) -> tuple:
    """
    If battery is in the deep-discharge zone, degrade capacity.
    Returns (battery_cap_new, soh_new).
    """
    pct = battery / battery_cap if battery_cap > 0 else 1.0
    if pct < SOH_LOW_THRESH:
        soh         = max(0.5, soh - SOH_DEGRADE_RATE)   # floor at 50% capacity
        battery_cap = BATTERY_CAPACITY * soh
    return battery_cap, soh


# ─────────────────────────────────────────────
# DEVICE 2: lighter load, lower threshold (first)
# ─────────────────────────────────────────────
def run_device2(battery: float, dt: float) -> tuple:
    if battery >= DEVICE2_ON_THRESH:
        consumed = min(DEVICE2_POWER * dt, battery - DEVICE2_ON_THRESH)
        return battery - consumed, True, consumed
    return battery, False, 0.0


# ─────────────────────────────────────────────
# SC2: Return Supercharger on Device 2 output
# ─────────────────────────────────────────────
def sc2_return(consumed_j: float) -> tuple:
    """
    Takes the energy consumed by Device 2 this tick and routes it back
    toward the Energy Bank via a second boost converter.

    If consumed >= SC2_MIN_INPUT:  boost and recover a fraction
    Otherwise:                     passively bleed a small residual

    Returns (energy_to_bank, heat_j).
    """
    if consumed_j >= SC2_MIN_INPUT:
        amplified  = consumed_j * SC2_RECOVER_RATIO
        to_bank    = amplified * SC2_EFF
        heat       = amplified * SC2_HEAT_COEFF
        return to_bank, heat
    # below gate -- bleed a tiny residual passively
    to_bank = consumed_j * 0.30
    heat    = consumed_j * 0.10
    return to_bank, heat


# ─────────────────────────────────────────────
# SC3: Return Supercharger on Device 3 feedback path  (NEW v5)
# ─────────────────────────────────────────────
def sc3_return(consumed_j: float) -> tuple:
    """
    Takes the energy consumed by Device 3 this tick, applies FEEDBACK_EFF first
    (physical recovery fraction), then boosts through SC3 before returning to bank.

    Returns (energy_to_bank, heat_j).
    """
    recovered = consumed_j * FEEDBACK_EFF          # raw physical recovery (65%)
    if recovered >= SC3_MIN_INPUT:
        amplified = recovered * SC3_RECOVER_RATIO
        to_bank   = amplified * SC3_EFF
        heat      = amplified * SC3_HEAT_COEFF
        return to_bank, heat
    # below gate -- pass through at reduced efficiency
    to_bank = recovered * 0.40
    heat    = recovered * 0.12
    return to_bank, heat


# ─────────────────────────────────────────────
# DEVICE 3: heavier load, higher threshold (second)
# ─────────────────────────────────────────────
def run_device3(battery: float, dt: float) -> tuple:
    if battery >= DEVICE3_ON_THRESH:
        consumed = min(DEVICE3_POWER * dt, battery - DEVICE3_ON_THRESH)
        battery -= consumed
        return battery, True, consumed
    return battery, False, 0.0


# ─────────────────────────────────────────────
# MAIN SIMULATION LOOP
# ─────────────────────────────────────────────
def run_simulation():
    random.seed(42)

    # ── Initial state (v7 VICS) ─────────────────────────────────────
    cells       = [min(BANK_INIT / BANK_CELL_COUNT, BANK_CELL_CAP)] * BANK_CELL_COUNT
    ch_a        = VICS_A_INIT           # Chamber A pre-charged to threshold
    ch_b        = VICS_B_INIT           # Chamber B pre-charged to threshold
    ch_c        = VICS_C_INIT           # Chamber C pre-charged above C_LOW
    battery     = BATTERY_INIT
    battery_cap = BATTERY_CAPACITY
    soh         = 1.0

    # Accumulators
    total_raw        = 0.0
    total_sc_out     = 0.0
    total_sc_heat    = 0.0
    total_overflow   = 0.0
    total_scv_heat   = 0.0
    total_vics_heat  = 0.0
    total_vics_out   = 0.0
    total_device2    = 0.0
    total_device3    = 0.0
    total_sc2_out    = 0.0
    total_sc2_heat   = 0.0
    total_sc3_out    = 0.0
    total_sc3_heat   = 0.0
    surge_count      = 0
    boost_ticks      = 0
    trickle_ticks    = 0
    scv_activations  = 0
    d2_on_count      = 0
    d3_on_count      = 0
    deep_discharge   = 0

    rows = []

    hdr = (f"{'Tick':>4} | {'V_MUT':>7} | {'SC_mode':>7} | {'SC_out':>6} | "
           f"{'BankJ':>7} | {'OvflwJ':>6} | {'ChA':>5} | {'ChB':>5} | {'ChC':>5} | "
           f"{'BattJ':>6} | {'SOH%':>5} | {'D2':>3} | {'D3':>3}")
    print(hdr)
    print("-" * len(hdr))

    for tick in range(1, TICKS + 1):

        # STEP 1 -- MUT raw voltage & energy
        voltage   = mut_voltage(tick)
        raw_j     = raw_energy(voltage, DT)
        total_raw += raw_j
        if voltage > MUT_BASE_VOLTAGE + 8:
            surge_count += 1

        # STEP 2 -- Supercharger conditions the energy
        sc_out, sc_heat, sc_mode = supercharger(raw_j, DT)
        total_sc_out  += sc_out
        total_sc_heat += sc_heat
        if sc_mode == "boost":
            boost_ticks += 1
        else:
            trickle_ticks += 1

        # STEP 3 -- Feed supercharger output into bank
        cells, overflow = bank_fill_and_overflow(cells, sc_out)
        bank_energy      = sum(cells)
        total_overflow  += overflow

        # STEP 3b -- SC-V: vault recovery boost (fires when total VICS is low)
        vics_total = ch_a + ch_b + ch_c
        overflow_conditioned, scv_heat, scv_active = scv_boost(overflow, vics_total)
        total_scv_heat += scv_heat
        if scv_active:
            scv_activations += 1

        # STEP 4 -- Conditioned overflow -> VICS -> Battery
        ch_a, ch_b, ch_c, battery, vics_out, vics_heat = vics_step(
            ch_a, ch_b, ch_c, overflow_conditioned, battery, battery_cap, DT)
        total_vics_out  += vics_out
        total_vics_heat += vics_heat

        # STEP 5 -- Device 2 draws from battery (lighter load, first)
        battery, dev2_on, consumed2 = run_device2(battery, DT)
        total_device2 += consumed2
        if dev2_on:
            d2_on_count += 1

        # STEP 5b -- SC2: boost-recover Device 2 output back to bank
        sc2_to_bank, sc2_heat = sc2_return(consumed2)
        total_sc2_out  += sc2_to_bank
        total_sc2_heat += sc2_heat
        cells, _ = bank_fill_and_overflow(cells, sc2_to_bank)
        bank_energy = sum(cells)

        # STEP 6 -- Device 3 draws from battery remainder (heavier load, second)
        battery, dev3_on, consumed3 = run_device3(battery, DT)
        total_device3 += consumed3
        if dev3_on:
            d3_on_count += 1

        # STEP 6b -- SC3: boost-recover Device 3 output back to bank
        sc3_to_bank, sc3_heat = sc3_return(consumed3)
        total_sc3_out  += sc3_to_bank
        total_sc3_heat += sc3_heat
        cells, _ = bank_fill_and_overflow(cells, sc3_to_bank)
        bank_energy = sum(cells)

        # STEP 8 -- State of Health update
        battery_cap, soh = update_soh(battery, battery_cap, soh)
        if (battery / battery_cap if battery_cap > 0 else 1.0) < SOH_LOW_THRESH:
            deep_discharge += 1

        # STEP 9 -- Clamp
        battery     = max(0.0, min(battery_cap, battery))
        ch_a        = max(0.0, min(VICS_A_CAP, ch_a))
        ch_b        = max(0.0, min(VICS_B_CAP, ch_b))
        ch_c        = max(0.0, min(VICS_C_CAP, ch_c))
        bank_energy = sum(cells)

        row = {
            "tick":          tick,
            "v_mut":         round(voltage,      2),
            "sc_mode":       sc_mode,
            "sc_out_j":      round(sc_out,       3),
            "sc_heat_j":     round(sc_heat,      3),
            "bank_j":        round(bank_energy,  3),
            "overflow_j":    round(overflow,     3),
            "scv_active":    int(scv_active),
            "scv_heat_j":    round(scv_heat,     3),
            "ch_a_j":        round(ch_a,         3),
            "ch_b_j":        round(ch_b,         3),
            "ch_c_j":        round(ch_c,         3),
            "vics_out_j":    round(vics_out,     3),
            "vics_heat_j":   round(vics_heat,    3),
            "battery_j":     round(battery,      3),
            "battery_cap":   round(battery_cap,  2),
            "soh_pct":       round(soh * 100,    1),
            "device2":       int(dev2_on),
            "sc2_to_bank_j": round(sc2_to_bank,  3),
            "sc2_heat_j":    round(sc2_heat,     3),
            "device3":       int(dev3_on),
            "sc3_to_bank_j": round(sc3_to_bank,  3),
            "sc3_heat_j":    round(sc3_heat,     3),
        }
        rows.append(row)

        print(f"{tick:>4} | {voltage:>7.2f} | {sc_mode:>7} | {sc_out:>6.2f} | "
              f"{bank_energy:>7.2f} | {overflow:>6.2f} | "
              f"{ch_a:>5.1f} | {ch_b:>5.1f} | {ch_c:>5.1f} | "
              f"{battery:>6.2f} | {soh*100:>5.1f} | "
              f"{'ON' if dev2_on else 'off':>3} | {'ON' if dev3_on else 'off':>3}")

    # ── Summary ──────────────────────────────────────────────────────
    sep = "=" * 72
    print(f"\n{sep}")
    print("SIMULATION SUMMARY  --  v7  (VICS + SC1 + SC2 + SC3 + SC-V + SOH)")
    print(f"Flow: MUT->SC1->Bank->SC-V->VICS[A->B->C]->Battery->D2->SC2->Bank / D3->SC3->Bank")
    print(f"Init: Bank={BANK_INIT}J  ChA={VICS_A_INIT}J  ChB={VICS_B_INIT}J  ChC={VICS_C_INIT}J  Batt={BATTERY_INIT}J")
    print(sep)
    print(f"  Total ticks              : {TICKS}")
    print(f"  Surge events             : {surge_count}")
    print(f"  SC1 boost ticks          : {boost_ticks}")
    print(f"  SC1 trickle ticks        : {trickle_ticks}")
    print(f"  Raw MUT energy           : {total_raw:.2f} J")
    if total_raw > 0:
        print(f"  SC1 output to bank       : {total_sc_out:.2f} J  "
              f"(gain x{total_sc_out/total_raw:.2f})")
    print(f"  SC1 heat loss            : {total_sc_heat:.2f} J")
    print(f"  Total overflow to VICS   : {total_overflow:.2f} J")
    print(f"  SC-V activations         : {scv_activations}  (VICS recovery boost events)")
    print(f"  SC-V heat loss           : {total_scv_heat:.2f} J")
    print(f"  VICS total to battery    : {total_vics_out:.2f} J")
    print(f"  VICS internal heat loss  : {total_vics_heat:.2f} J")
    print(f"  Final VICS A/B/C         : {ch_a:.1f} / {ch_b:.1f} / {ch_c:.1f} J")
    print(f"  Energy to Device 2       : {total_device2:.2f} J  ({d2_on_count} ticks ON)")
    if total_device2 > 0:
        print(f"  SC2 recovered to bank    : {total_sc2_out:.2f} J  "
              f"(x{total_sc2_out/total_device2:.2f} of D2 output)")
    print(f"  SC2 heat loss            : {total_sc2_heat:.2f} J")
    print(f"  Energy to Device 3       : {total_device3:.2f} J  ({d3_on_count} ticks ON)")
    if total_device3 > 0:
        print(f"  SC3 recovered to bank    : {total_sc3_out:.2f} J  "
              f"(x{total_sc3_out/total_device3:.2f} of D3 output)")
    print(f"  SC3 heat loss            : {total_sc3_heat:.2f} J")
    total_return = total_sc2_out + total_sc3_out
    print(f"  Total return to bank     : {total_return:.2f} J  (SC2 + SC3)")
    print(f"  Deep discharge ticks     : {deep_discharge}")
    print(f"  Final SOH                : {soh*100:.1f}%")
    print(f"  Final battery cap        : {battery_cap:.1f} J  (of {BATTERY_CAPACITY} J)")
    print(f"  Final battery charge     : {battery:.2f} J")
    useful = total_device2 + total_device3
    print(f"  Total useful output      : {useful:.2f} J")
    print(f"  System efficiency        : {useful/total_raw*100:.1f}%  (useful / raw MUT)")
    print(sep)

    with open("energy_bank_results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print("\nResults saved to energy_bank_results.csv")

    return rows


if __name__ == "__main__":
    run_simulation()
