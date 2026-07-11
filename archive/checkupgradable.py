#!/usr/bin/env python3
"""
Script to check for updatable packages in system site-packages directory.
Features: JSON output, resumable jobs, multiprocessing for speed, separate upgradable packages.
"""

import functools
import json
import os
import subprocess
import sys
from multiprocessing import Pool, cpu_count
from pathlib import Path
from typing import Dict, Set, Tuple

import pkg_resources

# Configuration
OUTPUT_FILE = "/sdcard/s4u.json"
UPGRADABLE_FILE = "/sdcard/upgradable.json"
CHECKPOINT_FILE = "/sdcard/checkpoint.json"
MAX_WORKERS = max(1, cpu_count() - 1)  # Leave one CPU free


def get_installed_packages() -> Dict[str, str]:
    """Get all installed packages and their versions from site-packages."""
    packages = {}
    try:
        # Get packages from the system site-packages
        for dist in pkg_resources.working_set:
            # Filter for system site-packages only
            if "site-packages" in str(dist.location):
                packages[dist.project_name] = dist.version
    except Exception as e:
        print(f"Error getting installed packages: {e}")
        sys.exit(1)
    return packages


def get_latest_version(package_name: str, current_version: str) -> Tuple[str, str, bool]:
    """
    Check latest version of a package from PyPI.
    Returns (package_name, latest_version, is_upgradable)
    """
    try:
        # Use pip index to check latest version
        result = subprocess.run(
            [sys.executable, "-m", "pip", "index", "versions", package_name], capture_output=True, text=True, timeout=10
        )

        if result.returncode == 0:
            # Parse output to find latest version
            for line in result.stdout.split("\n"):
                if "Available versions:" in line or "LATEST:" in line:
                    # Extract version number
                    parts = line.split()
                    for part in parts:
                        if part[0].isdigit() or part[0] == "v":
                            latest = part.strip(",)")
                            # Check if update is available
                            is_upgradable = compare_versions(latest, current_version)
                            return (package_name, latest, is_upgradable)
    except subprocess.TimeoutExpired:
        print(f"Timeout checking {package_name}")
    except Exception as e:
        print(f"Error checking {package_name}: {e}")

    return (package_name, current_version, False)


def compare_versions(latest: str, current: str) -> bool:
    """Compare two versions to see if latest is newer."""
    # Simple version comparison (can be enhanced)
    try:
        # Remove any prefixes (v, etc.)
        latest = latest.lstrip("vV")
        current = current.lstrip("vV")

        # Split into components
        latest_parts = [int(x) for x in latest.split(".") if x.isdigit()]
        current_parts = [int(x) for x in current.split(".") if x.isdigit()]

        # Compare each component
        for l, c in zip(latest_parts, current_parts):
            if l > c:
                return True
            elif l < c:
                return False

        # If all compared parts are equal, check length
        return len(latest_parts) > len(current_parts)
    except:
        # If comparison fails, do string comparison
        return latest != current


def load_checkpoint() -> Tuple[Set[str], Dict[str, Dict[str, str]]]:
    """Load previously processed packages from checkpoint."""
    processed_packages = set()
    results = {}

    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r") as f:
                checkpoint = json.load(f)
                processed_packages = set(checkpoint.get("processed", []))
                results = checkpoint.get("results", {})
            print(f"Resuming from checkpoint: {len(processed_packages)} packages already processed")
        except Exception as e:
            print(f"Error loading checkpoint: {e}")

    return processed_packages, results


def save_checkpoint(processed: Set[str], results: Dict) -> None:
    """Save current progress to checkpoint file."""
    checkpoint = {"processed": list(processed), "results": results, "total_processed": len(processed)}
    try:
        with open(CHECKPOINT_FILE, "w") as f:
            json.dump(checkpoint, f, indent=2)
    except Exception as e:
        print(f"Error saving checkpoint: {e}")


def process_packages_parallel(packages: Dict[str, str]) -> Dict[str, Dict[str, str]]:
    """Process packages in parallel using multiprocessing."""
    results = {}
    processed_packages, saved_results = load_checkpoint()
    results.update(saved_results)

    # Filter out already processed packages
    pending_packages = {name: version for name, version in packages.items() if name not in processed_packages}

    if not pending_packages:
        print("All packages already processed!")
        return results

    print(f"Processing {len(pending_packages)} packages using {MAX_WORKERS} workers...")

    # Create partial function with version info
    check_func = functools.partial(check_package_version, packages=packages)

    # Process in chunks for better progress tracking
    package_items = list(pending_packages.items())
    chunk_size = max(1, len(package_items) // 100)  # Show progress every ~1%

    with Pool(processes=MAX_WORKERS) as pool:
        for i, (package_name, version, latest, is_upgradable) in enumerate(
            pool.imap_unordered(check_func, package_items), 1
        ):
            results[package_name] = {"installed_version": version, "latest_version": latest}
            processed_packages.add(package_name)

            # Save progress periodically
            if i % 10 == 0:  # Save checkpoint every 10 packages
                save_checkpoint(processed_packages, results)
                print(f"Progress: {i}/{len(pending_packages)} packages checked")

            # Show progress
            if i % chunk_size == 0 or i == len(pending_packages):
                percent = (i / len(pending_packages)) * 100
                print(f"Progress: {percent:.1f}% ({i}/{len(pending_packages)})")

    # Final checkpoint save
    save_checkpoint(processed_packages, results)

    return results


def check_package_version(package_info: Tuple[str, str], packages: Dict) -> Tuple[str, str, str, bool]:
    """Wrapper function for multiprocessing to check a single package."""
    package_name, current_version = package_info
    package_name, latest_version, is_upgradable = get_latest_version(package_name, current_version)
    return (package_name, current_version, latest_version, is_upgradable)


def save_results(results: Dict) -> None:
    """Save results to JSON files."""
    # Save all results
    try:
        # Ensure directory exists
        Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)

        with open(OUTPUT_FILE, "w") as f:
            json.dump(results, f, indent=2)
        print(f"All results saved to {OUTPUT_FILE}")
    except Exception as e:
        print(f"Error saving results: {e}")

    # Save only upgradable packages
    upgradable = {name: info for name, info in results.items() if info["installed_version"] != info["latest_version"]}

    try:
        with open(UPGRADABLE_FILE, "w") as f:
            json.dump(upgradable, f, indent=2)
        print(f"Upgradable packages ({len(upgradable)}) saved to {UPGRADABLE_FILE}")
    except Exception as e:
        print(f"Error saving upgradable packages: {e}")


def main() -> None:
    """Main function to orchestrate the package checking."""
    print("Starting package update checker...")
    print(f"Output directory: /sdcard/")

    # Get installed packages
    print("Scanning installed packages in system site-packages...")
    installed_packages = get_installed_packages()
    print(f"Found {len(installed_packages)} installed packages")

    if not installed_packages:
        print("No packages found in system site-packages!")
        return

    # Process packages in parallel
    results = process_packages_parallel(installed_packages)

    # Save final results
    save_results(results)

    # Summary
    upgradable_count = sum(1 for info in results.values() if info["installed_version"] != info["latest_version"])

    print(f"\nSummary:")
    print(f"Total packages checked: {len(results)}")
    print(f"Upgradable packages: {upgradable_count}")
    print(f"Up-to-date packages: {len(results) - upgradable_count}")

    # Clean up checkpoint if completed successfully
    if len(results) == len(installed_packages):
        try:
            os.remove(CHECKPOINT_FILE)
            print("Checkpoint file cleaned up")
        except:
            pass


if __name__ == "__main__":
    main()
