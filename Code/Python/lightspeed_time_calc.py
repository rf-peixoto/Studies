#!/usr/bin/env python3
"""
Relativistic Travel / Time Dilation Calculator

This is a special-relativity calculator for inertial, constant-speed travel.
It deliberately ignores acceleration, deceleration, gravity, fuel, navigation,
and the fact that a realistic trip requires a changing reference frame when
turning around.

Supported modes:

1. Traveler-time mode:
   You provide the proper time experienced aboard the ship and the ship speed.
   The script calculates how much coordinate time passes on Earth.

2. Distance mode:
   You provide an Earth-frame distance and the ship speed.
   The script calculates both Earth-frame travel time and ship proper time.

The core equations are:

    beta = v / c
    gamma = 1 / sqrt(1 - beta^2)

    Earth time from traveler time:
        t_earth = tau_ship * gamma

    Traveler time from Earth-frame distance:
        t_earth = distance / velocity
        tau_ship = t_earth / gamma

When distance is given in light-years and speed is given as a fraction of c,
Earth-frame travel time in years is simply:

    t_earth_years = distance_ly / beta
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass


# Julian year/calendar approximations.
DAYS_PER_YEAR = 365.25
DAYS_PER_MONTH = DAYS_PER_YEAR / 12
HOURS_PER_DAY = 24
MINUTES_PER_DAY = 24 * 60
SECONDS_PER_DAY = 24 * 60 * 60

# Distance conversions.
# 1 light-year is the distance light travels in one Julian year.
METERS_PER_LIGHT_YEAR = 9_460_730_472_580_800
KM_PER_LIGHT_YEAR = METERS_PER_LIGHT_YEAR / 1000
AU_PER_LIGHT_YEAR = 63_241.07708426628


TIME_UNITS_TO_DAYS = {
    "s": 1 / SECONDS_PER_DAY,
    "sec": 1 / SECONDS_PER_DAY,
    "second": 1 / SECONDS_PER_DAY,
    "seconds": 1 / SECONDS_PER_DAY,

    "min": 1 / MINUTES_PER_DAY,
    "minute": 1 / MINUTES_PER_DAY,
    "minutes": 1 / MINUTES_PER_DAY,

    "h": 1 / HOURS_PER_DAY,
    "hr": 1 / HOURS_PER_DAY,
    "hour": 1 / HOURS_PER_DAY,
    "hours": 1 / HOURS_PER_DAY,

    "d": 1,
    "day": 1,
    "days": 1,

    "m": DAYS_PER_MONTH,
    "mo": DAYS_PER_MONTH,
    "month": DAYS_PER_MONTH,
    "months": DAYS_PER_MONTH,

    "y": DAYS_PER_YEAR,
    "yr": DAYS_PER_YEAR,
    "year": DAYS_PER_YEAR,
    "years": DAYS_PER_YEAR,
}


DISTANCE_UNITS_TO_LIGHT_YEARS = {
    "ly": 1,
    "lightyear": 1,
    "lightyears": 1,
    "light-year": 1,
    "light-years": 1,

    "au": 1 / AU_PER_LIGHT_YEAR,
    "astronomicalunit": 1 / AU_PER_LIGHT_YEAR,
    "astronomicalunits": 1 / AU_PER_LIGHT_YEAR,
    "astronomical-unit": 1 / AU_PER_LIGHT_YEAR,
    "astronomical-units": 1 / AU_PER_LIGHT_YEAR,

    "km": 1 / KM_PER_LIGHT_YEAR,
    "kilometer": 1 / KM_PER_LIGHT_YEAR,
    "kilometers": 1 / KM_PER_LIGHT_YEAR,

    "m": 1 / METERS_PER_LIGHT_YEAR,
    "meter": 1 / METERS_PER_LIGHT_YEAR,
    "meters": 1 / METERS_PER_LIGHT_YEAR,
}


@dataclass(frozen=True)
class Duration:
    days: float

    @property
    def years(self) -> float:
        return self.days / DAYS_PER_YEAR

    @property
    def months(self) -> float:
        return self.days / DAYS_PER_MONTH

    @property
    def hours(self) -> float:
        return self.days * HOURS_PER_DAY

    @property
    def minutes(self) -> float:
        return self.days * MINUTES_PER_DAY

    @property
    def seconds(self) -> float:
        return self.days * SECONDS_PER_DAY


def normalize_unit(unit: str) -> str:
    """Normalize user-entered unit strings."""
    return unit.strip().lower().replace(" ", "").replace("_", "-")


def lorentz_factor(beta: float) -> float:
    """
    Return gamma for beta = v / c.

    beta must satisfy 0 <= beta < 1.
    """
    if not 0 <= beta < 1:
        raise ValueError("beta must be at least 0 and lower than 1")
    return 1 / math.sqrt(1 - beta * beta)


def speed_percent_to_beta(speed_percent: float) -> float:
    """Convert percentage of light speed to beta = v / c."""
    if not 0 <= speed_percent < 100:
        raise ValueError("speed must be at least 0% and lower than 100%")
    return speed_percent / 100


def convert_time_to_days(amount: float, unit: str) -> float:
    """Convert a time duration to days."""
    if amount < 0:
        raise ValueError("time cannot be negative")

    normalized = normalize_unit(unit)
    if normalized not in TIME_UNITS_TO_DAYS:
        raise ValueError(f"unsupported time unit: {unit!r}")

    return amount * TIME_UNITS_TO_DAYS[normalized]


def convert_distance_to_light_years(amount: float, unit: str) -> float:
    """Convert an Earth-frame distance to light-years."""
    if amount < 0:
        raise ValueError("distance cannot be negative")

    normalized = normalize_unit(unit)
    if normalized not in DISTANCE_UNITS_TO_LIGHT_YEARS:
        raise ValueError(f"unsupported distance unit: {unit!r}")

    return amount * DISTANCE_UNITS_TO_LIGHT_YEARS[normalized]


def show_duration(label: str, duration: Duration) -> None:
    """Print one duration in several units."""
    print(f"\n{label}")
    print(f"    Years:    {duration.years:,.9g}")
    print(f"    Months:   {duration.months:,.9g}")
    print(f"    Days:     {duration.days:,.9g}")
    print(f"    Hours:    {duration.hours:,.9g}")
    print(f"    Minutes:  {duration.minutes:,.9g}")
    print(f"    Seconds:  {duration.seconds:,.9g}")


def show_distance(label: str, distance_ly: float) -> None:
    """Print one distance in several units."""
    print(f"\n{label}")
    print(f"    Light-years:          {distance_ly:,.9g}")
    print(f"    Astronomical units:   {distance_ly * AU_PER_LIGHT_YEAR:,.9g}")
    print(f"    Kilometers:           {distance_ly * KM_PER_LIGHT_YEAR:,.9g}")
    print(f"    Meters:               {distance_ly * METERS_PER_LIGHT_YEAR:,.9g}")


def read_float(prompt: str, *, minimum: float | None = None, maximum: float | None = None) -> float:
    """Read and validate a floating-point number."""
    while True:
        raw = input(prompt).strip()
        try:
            value = float(raw)
        except ValueError:
            print("[!] Please enter a valid number.\n")
            continue

        if minimum is not None and value < minimum:
            print(f"[!] Value must be at least {minimum}.\n")
            continue

        if maximum is not None and value >= maximum:
            print(f"[!] Value must be lower than {maximum}.\n")
            continue

        return value


def read_choice(prompt: str, valid_choices: set[str]) -> str:
    """Read a menu choice."""
    while True:
        choice = input(prompt).strip().lower()
        if choice in valid_choices:
            return choice
        print(f"[!] Select one of: {', '.join(sorted(valid_choices))}.\n")


def read_time_unit() -> str:
    print("""
Supported time units:
    seconds, minutes, hours, days, months, years
Examples:
    seconds | minutes | hours | days | months | years
""")
    while True:
        unit = input("Time unit: ").strip()
        if normalize_unit(unit) in TIME_UNITS_TO_DAYS:
            return unit
        print("[!] Unsupported time unit. Try: days, months, or years.\n")


def read_distance_unit() -> str:
    print("""
Supported distance units:
    light-years, AU, kilometers, meters
Examples:
    ly | au | km | m
""")
    while True:
        unit = input("Distance unit: ").strip()
        if normalize_unit(unit) in DISTANCE_UNITS_TO_LIGHT_YEARS:
            return unit
        print("[!] Unsupported distance unit. Try: ly, au, km, or m.\n")


def print_header(title: str) -> None:
    print()
    print("=" * 72)
    print(title.center(72))
    print("=" * 72)


def show_assumptions() -> None:
    print("""
Physics model:
    - Special relativity only.
    - Constant velocity relative to Earth.
    - No acceleration, deceleration, gravity, fuel limits, or orbital mechanics.
    - Earth is treated as an inertial reference frame.
""")


def calculate_from_traveler_time() -> None:
    """
    Given ship proper time and velocity, calculate Earth elapsed time.
    """
    print_header("MODE 1: TRAVELER TIME -> EARTH TIME")

    amount = read_float("How much time passes for the traveler aboard the ship? ", minimum=0)
    unit = read_time_unit()
    speed_percent = read_float("Speed as percentage of light speed: ", minimum=0, maximum=100)

    beta = speed_percent_to_beta(speed_percent)
    gamma = lorentz_factor(beta)

    traveler_days = convert_time_to_days(amount, unit)
    earth_days = traveler_days * gamma
    difference_days = earth_days - traveler_days

    earth_years = earth_days / DAYS_PER_YEAR
    earth_frame_distance_ly = beta * earth_years
    ship_frame_distance_ly = earth_frame_distance_ly / gamma

    print_header("RESULT")
    print(f"Speed:          {speed_percent:g}% of light speed")
    print(f"Beta, v/c:      {beta:,.12g}")
    print(f"Lorentz gamma:  {gamma:,.12g}")

    show_duration("Traveler proper time:", Duration(traveler_days))
    show_duration("Earth elapsed time:", Duration(earth_days))
    show_duration("Earth experiences this much more time:", Duration(difference_days))

    if beta > 0:
        show_distance("Distance covered in Earth's frame:", earth_frame_distance_ly)
        show_distance("Same route length in the ship's frame due to length contraction:", ship_frame_distance_ly)
    else:
        print("\nAt 0% of light speed, there is no time dilation and no distance traveled.")


def calculate_from_distance() -> None:
    """
    Given Earth-frame distance and velocity, calculate Earth time and ship time.
    """
    print_header("MODE 2: DISTANCE + SPEED -> TRAVEL TIMES")

    distance_amount = read_float("Earth-frame distance to destination: ", minimum=0)
    distance_unit = read_distance_unit()
    speed_percent = read_float("Speed as percentage of light speed: ", minimum=0, maximum=100)

    beta = speed_percent_to_beta(speed_percent)
    if beta == 0:
        print("\n[!] At 0% of light speed, the ship never reaches the destination.\n")
        return

    gamma = lorentz_factor(beta)
    distance_ly = convert_distance_to_light_years(distance_amount, distance_unit)

    # Since c = 1 light-year per Julian year, time in Earth years is d / beta.
    earth_years = distance_ly / beta
    earth_days = earth_years * DAYS_PER_YEAR
    traveler_days = earth_days / gamma
    difference_days = earth_days - traveler_days
    ship_frame_distance_ly = distance_ly / gamma

    print_header("RESULT")
    print(f"Speed:          {speed_percent:g}% of light speed")
    print(f"Beta, v/c:      {beta:,.12g}")
    print(f"Lorentz gamma:  {gamma:,.12g}")

    show_distance("Earth-frame distance:", distance_ly)
    show_distance("Distance in the ship's frame due to length contraction:", ship_frame_distance_ly)

    show_duration("Earth elapsed travel time:", Duration(earth_days))
    show_duration("Traveler proper time aboard the ship:", Duration(traveler_days))
    show_duration("Earth experiences this much more time:", Duration(difference_days))


def main() -> int:
    print_header("RELATIVISTIC TRAVEL CALCULATOR")
    show_assumptions()

    while True:
        print("""
Choose calculation mode:
    [1] I know the time experienced aboard the ship
    [2] I know the Earth-frame distance to the destination
    [q] Quit
""")

        choice = read_choice("Select [1/2/q]: ", {"1", "2", "q", "quit"})

        if choice in {"q", "quit"}:
            print("\nSafe travels.\n")
            return 0

        try:
            if choice == "1":
                calculate_from_traveler_time()
            elif choice == "2":
                calculate_from_distance()
        except ValueError as exc:
            print(f"\n[!] {exc}\n")

        again = read_choice("\nCalculate another journey? [Y/n]: ", {"", "y", "yes", "n", "no"})
        if again in {"n", "no"}:
            print("\nSafe travels.\n")
            return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n\nCalculator closed.\n")
        raise SystemExit(130)
