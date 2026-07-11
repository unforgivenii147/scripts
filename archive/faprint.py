# persian_text.py

# Persian letter forms (simplified subset)
PERSIAN_LETTERS = {
    "ا": ("\u0627", "\ufe8d", "\ufe8e", "\ufe8e"),  # Alef
    "ب": ("\u0628", "\ufe8f", "\ufe91", "\ufe90"),  # Beh
    "پ": ("\u067e", "\ufb56", "\ufb58", "\ufb57"),  # Peh
    "ت": ("\u062a", "\ufe95", "\ufe97", "\ufe96"),  # Teh
    "ث": ("\u062b", "\ufe99", "\ufe9b", "\ufe9a"),  # Theh
    "ج": ("\u062c", "\ufe9d", "\ufe9f", "\ufe9e"),  # Jeem
    "چ": ("\u0686", "\ufb7a", "\ufb7c", "\ufb7b"),  # Cheh
    "ح": ("\u062d", "\ufea1", "\ufea3", "\ufea2"),  # Hah
    "خ": ("\u062e", "\ufea5", "\ufea7", "\ufea6"),  # Khah
    "د": ("\u062f", "\ufea9", "\ufeaa", "\ufeaa"),  # Dal
    "ذ": ("\u0630", "\ufeab", "\ufeac", "\ufeac"),  # Thal
    "ر": ("\u0631", "\ufead", "\ufeae", "\ufeae"),  # Reh
    "ز": ("\u0632", "\ufeaf", "\ufeb0", "\ufeb0"),  # Zeh
    "ژ": ("\u0698", "\ufb8a", "\ufb8b", "\ufb8b"),  # Jeh
    "س": ("\u0633", "\ufeb1", "\ufeb3", "\ufeb2"),  # Seen
    "ش": ("\u0634", "\ufeb5", "\ufeb7", "\ufeb6"),  # Sheen
    "ص": ("\u0635", "\ufeb9", "\ufebb", "\ufeba"),  # Sad
    "ض": ("\u0636", "\ufebd", "\ufebf", "\ufebe"),  # Zad
    "ط": ("\u0637", "\ufec1", "\ufec3", "\ufec2"),  # Ta
    "ظ": ("\u0638", "\ufec5", "\ufec7", "\ufec6"),  # Za
    "ع": ("\u0639", "\ufec9", "\ufecb", "\ufeca"),  # Ain
    "غ": ("\u063a", "\ufecd", "\ufecf", "\ufece"),  # Ghein
    "ف": ("\u0641", "\ufed1", "\ufed3", "\ufed2"),  # Feh
    "ق": ("\u0642", "\ufed5", "\ufed7", "\ufed6"),  # Qaf
    "ک": ("\u06a9", "\ufb8e", "\ufb90", "\ufb8f"),  # Kaf
    "گ": ("\u06af", "\ufb92", "\ufb94", "\ufb93"),  # Gaf
    "ل": ("\u0644", "\ufedf", "\ufee1", "\ufee0"),  # Lam
    "م": ("\u0645", "\ufee3", "\ufee5", "\ufee4"),  # Meem
    "ن": ("\u0646", "\ufee7", "\ufee9", "\ufee8"),  # Noon
    "و": ("\u0648", "\ufeee", "\ufeef", "\ufeef"),  # Waw
    "ه": ("\u0647", "\ufeeb", "\ufeed", "\ufeec"),  # Heh
    "ی": ("\u06cc", "\ufbfc", "\ufbfe", "\ufbfd"),  # Yeh
    " ": (" ", " ", " ", " "),  # Space
}

# Letters that cannot connect to the next letter
NON_CONNECTING = {"ا", "د", "ذ", "ر", "ز", "ژ", "و"}


def reshape_word(word: str) -> str:
    """Convert Persian letters to contextual forms."""
    reshaped = []
    length = len(word)
    for i, char in enumerate(word):
        if char not in PERSIAN_LETTERS:
            reshaped.append(char)
            continue

        prev_char = word[i - 1] if i > 0 else ""
        next_char = word[i + 1] if i < length - 1 else ""

        connects_prev = prev_char and prev_char not in NON_CONNECTING and prev_char in PERSIAN_LETTERS
        connects_next = next_char and char not in NON_CONNECTING and next_char in PERSIAN_LETTERS

        forms = PERSIAN_LETTERS[char]

        if connects_prev and connects_next:
            reshaped.append(forms[2])  # Medial
        elif connects_prev:
            reshaped.append(forms[3])  # Final
        elif connects_next:
            reshaped.append(forms[1])  # Initial
        else:
            reshaped.append(forms[0])  # Isolated

    return "".join(reshaped)


def reshape_sentence(sentence: str) -> str:
    """Reshape a full Persian sentence and reverse word order for RTL."""
    words = sentence.split(" ")
    reshaped_words = [reshape_word(word) for word in words]
    # Reverse words for basic RTL display
    return " ".join(reversed(reshaped_words))


if __name__ == "__main__":
    s = "سلام دنیا"
    print(reshape_sentence(s))
