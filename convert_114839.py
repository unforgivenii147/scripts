import json
import re


def parse_gitsources_file(input_file, output_file):
    """
    Parse a markdown file with GitHub links and convert to JSON format.
    Format: 《description》(venue) GitHub: https://github.com/...
    Deletes successfully parsed lines from the input file.
    """
    results = []
    remaining_lines = []
    parsed_count = 0

    with open(input_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        original_line = line
        line = line.strip()

        if not line:
            remaining_lines.append(original_line)
            continue

        # Extract description between 《 and 》
        description_match = re.search(r"《([^》]+)》", line)
        if not description_match:
            remaining_lines.append(original_line)
            continue

        # Extract URL after "GitHub: "
        url_match = re.search(r"GitHub:\s*(https?://[^\s]+)", line)
        if not url_match:
            remaining_lines.append(original_line)
            continue

        # If we get here, parsing was successful
        description = description_match.group(1)
        url = url_match.group(1)

        results.append({"url": url, "description": description})
        parsed_count += 1
        # Don't add this line to remaining_lines (it will be deleted)

    # Write remaining lines back to the input file
    with open(input_file, "w", encoding="utf-8") as f:
        f.writelines(remaining_lines)

    # Write JSON output
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Successfully parsed {parsed_count} entries")
    print(f"Remaining lines in {input_file}: {len(remaining_lines)}")
    print(f"JSON saved to {output_file}")


if __name__ == "__main__":
    parse_gitsources_file("gitsources.md", "git.json")
