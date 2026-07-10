#!/usr/bin/env python3

import math


# Approximate astronomical/calendar conversions
DAYS_PER_YEAR = 365.25
DAYS_PER_MONTH = DAYS_PER_YEAR / 12


def convert_to_days(amount, unit):
    """Convert the traveler's input into days."""

    units = {
        "s": 1 / 86400,
        "sec": 1 / 86400,
        "second": 1 / 86400,
        "seconds": 1 / 86400,

        "min": 1 / 1440,
        "minute": 1 / 1440,
        "minutes": 1 / 1440,

        "h": 1 / 24,
        "hour": 1 / 24,
        "hours": 1 / 24,

        "d": 1,
        "day": 1,
        "days": 1,

        "m": DAYS_PER_MONTH,
        "month": DAYS_PER_MONTH,
        "months": DAYS_PER_MONTH,

        "y": DAYS_PER_YEAR,
        "year": DAYS_PER_YEAR,
        "years": DAYS_PER_YEAR,
    }

    return amount * units[unit]


def show_all_units(days):
    """Show the same duration in every supported time unit."""

    years = days / DAYS_PER_YEAR
    months = days / DAYS_PER_MONTH
    hours = days * 24
    minutes = hours * 60
    seconds = minutes * 60

    print(f"    Years:    {years:,.6f}")
    print(f"    Months:   {months:,.6f}")
    print(f"    Days:     {days:,.6f}")
    print(f"    Hours:    {hours:,.2f}")
    print(f"    Minutes:  {minutes:,.2f}")
    print(f"    Seconds:  {seconds:,.2f}")


print()
print("=" * 64)
print("              RELATIVISTIC TRAVEL CALCULATOR")
print("=" * 64)

print("""
Imagine that you are aboard a spacecraft.

Enter how long YOU experience aboard the spacecraft and how
fast it is moving. The calculator will tell you how much time
passes on Earth.
""")

while True:

    try:

        # --------------------------------------------------
        # Traveler time
        # --------------------------------------------------

        amount = float(
            input("How long do you experience aboard the ship? ")
        )

        if amount < 0:
            print("\n[!] Time cannot be negative.\n")
            continue

        # --------------------------------------------------
        # Unit
        # --------------------------------------------------

        print("""
Choose the time unit:

    [1] Days
    [2] Months
    [3] Years
""")

        choice = input("Select [1-3]: ").strip()

        unit_choices = {
            "1": "days",
            "2": "months",
            "3": "years",
        }

        if choice not in unit_choices:
            print("\n[!] Select 1, 2, or 3.\n")
            continue

        selected_unit = unit_choices[choice]

        # --------------------------------------------------
        # Velocity
        # --------------------------------------------------

        speed = float(
            input(
                "\nHow fast is the spacecraft?\n"
                "Enter percentage of light speed: "
            )
        )

        if not 0 <= speed < 100:
            print(
                "\n[!] Velocity must be at least 0% "
                "and lower than 100%.\n"
            )
            continue

        # --------------------------------------------------
        # Relativistic calculations
        # --------------------------------------------------

        speed_fraction = speed / 100

        gamma = 1 / math.sqrt(
            1 - speed_fraction**2
        )

        traveler_days = convert_to_days(
            amount,
            selected_unit
        )

        earth_days = traveler_days * gamma

        difference_days = (
            earth_days - traveler_days
        )

        # --------------------------------------------------
        # Results
        # --------------------------------------------------

        print()
        print("=" * 64)
        print("                         RESULT")
        print("=" * 64)

        print(
            f"\nYou travel for {amount:g} "
            f"{selected_unit} at {speed:g}% "
            f"of the speed of light."
        )

        print(
            "\nDuring your journey, you experience:"
        )

        show_all_units(traveler_days)

        print(
            "\nMeanwhile, the following amount of "
            "time passes on Earth:"
        )

        show_all_units(earth_days)

        print(
            "\nEarth experiences this much MORE "
            "time than you:"
        )

        show_all_units(difference_days)

        print(
            "\nRelativistic information:"
        )

        print(
            f"    Speed:          {speed:g}% "
            f"of light speed"
        )

        print(
            f"    Lorentz factor: {gamma:,.6f}"
        )

        print()
        print("=" * 64)

        # --------------------------------------------------
        # Repeat
        # --------------------------------------------------

        again = input(
            "\nCalculate another journey? [Y/n]: "
        ).strip().lower()

        if again in ("n", "no"):
            print("\nSafe travels.\n")
            break

        print()

    except ValueError:
        print(
            "\n[!] Please enter a valid number.\n"
        )

    except KeyboardInterrupt:
        print(
            "\n\nCalculator closed.\n"
        )
        break
