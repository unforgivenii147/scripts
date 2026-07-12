import json
import re


def preprocess_lines():
    """
    Preprocess the source file:
    1. If a line doesn't start with 《, append it to the previous line
    2. Replace Github: github.com with Github: https://github.com
    3. Replace https:// githhub.com with https://github.com
    """
    lines = []
    content = ""
    with open("gitsources.md", encoding="utf-8") as f:
        content = f.read()
    lines = content.splitlines()
    print(len(lines))
    processed_lines = []
    current_line = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check if line starts with 《
        if line.startswith("《"):
            # If we have a previous line, save it
            if current_line:
                processed_lines.append(current_line)
            # Start new line
            current_line = line
        else:
            # Append to previous line
            if current_line:
                current_line += line
            else:
                # If no previous line, start with this one
                current_line = line

    # Don't forget the last line
    if current_line:
        processed_lines.append(current_line)

    # Apply URL fixes
    fixed_lines = []
    for line in processed_lines:
        # Replace "Github: github.com" with "Github: https://github.com"
        line = re.sub(r"Github:\s*github\.com", "Github: https://github.com", line, flags=re.IGNORECASE)

        # Replace "https:// githhub.com" with "https://github.com"
        line = re.sub(r"https://\s*githhub\.com", "https://github.com", line, flags=re.IGNORECASE)

        fixed_lines.append(line)
    with open("gh2.md", "w") as fo:
        for k in fixed_lines:
            fo.write(f"{k}\n")
    return fixed_lines


def process_file(input_file, output_file):
    """
    Parse a markdown file with GitHub links and convert to JSON format.
    Format: 《description》(venue) GitHub: https://github.com/...
    Deletes successfully parsed lines from the input file.
    """
    results = []
    remaining_lines = []
    parsed_count = 0

    with open(input_file, "r", encoding="utf-8") as f:
        original_lines = f.readlines()

    # Preprocess the lines
    print("Preprocessing source file...")

    # Process each line
    for line in original_lines:
        original_line = line
        line = line.strip()

        if not line:
            continue

        # Extract description between 《 and 》
        description_match = re.search(r"《([^》]+)》", line)
        if not description_match:
            remaining_lines.append(original_line)
            continue

        # Extract URL after "GitHub: " or "Github: "
        url_match = re.search(r"Github?:\s*(https?://[^\s]+)", line, re.IGNORECASE)
        if not url_match:
            remaining_lines.append(original_line)
            continue

        # If we get here, parsing was successful
        description = description_match.group(1)
        url = url_match.group(1)

        results.append({"url": url, "description": description})
        parsed_count += 1

    # Write remaining lines back to the input file
    with open(input_file, "w", encoding="utf-8") as f:
        f.write("\n".join(remaining_lines))
        if remaining_lines:
            f.write("\n")  # Add trailing newline

    # Write JSON output
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Successfully parsed {parsed_count} entries")
    print(f"Remaining lines in {input_file}: {len(remaining_lines)}")
    print(f"JSON saved to {output_file}")


if __name__ == "__main__":
    process_file("gh2.md", "gh3.json")
