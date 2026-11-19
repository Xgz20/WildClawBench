#!/usr/bin/env python3
import argparse


def celsius_to_fahrenheit(value):
    """Convert a Celsius value to Fahrenheit."""
    return value * 9 / 5 - 32


def main():
    parser = argparse.ArgumentParser(description="Convert Celsius to Fahrenheit")
    parser.add_argument("value", type=float, help="temperature in Celsius")
    args = parser.parse_args()
    print(f"{celsius_to_fahrenheit(args.value):.1f}")


if __name__ == "__main__":
    main()
