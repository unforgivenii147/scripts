import re


def extract_names_from_md(input_file="models.md", output_file="extracted_names.txt"):
    """
    Extract names inside square brackets from a markdown file
    and save them to a text file.
    """
    try:
        # Read the input file
        with open(input_file, "r", encoding="utf-8") as file:
            content = file.read()

        # Find all patterns like [Name]
        # Using regex to find text between square brackets
        pattern = r"\[([^\]]+)\]"
        names = re.findall(pattern, content)

        # Remove duplicates while preserving order
        seen = set()
        unique_names = []
        for name in names:
            if name not in seen:
                seen.add(name)
                unique_names.append(name)

        # Write names to output file
        with open(output_file, "w", encoding="utf-8") as file:
            for name in unique_names:
                file.write(name + "\n")

        print(f"Successfully extracted {len(unique_names)} names!")
        print(f"Names saved to: {output_file}")

        # Optional: Print the extracted names
        print("\nExtracted names:")
        for name in unique_names:
            print(f"- {name}")

    except FileNotFoundError:
        print(f"Error: {input_file} not found in the current directory.")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    extract_names_from_md()
