#!/data/data/com.termux/files/usr/bin/python
"""
Folderize images based on face detection.
Images without human faces are moved to 'no_face' folder.
Images with faces stay in their original location.
"""

import os
import shutil
from pathlib import Path

try:
    import cv2

    FACE_DETECTION_AVAILABLE = True
except ImportError:
    FACE_DETECTION_AVAILABLE = False
    print("Warning: OpenCV not installed. Install with: pip install opencv-python")

# Supported image extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}


def is_image_file(filename):
    """Check if file is an image based on extension."""
    return Path(filename).suffix.lower() in IMAGE_EXTENSIONS


def has_human_face(image_path, cascade_path=None):
    """
    Detect if an image contains human faces.
    Returns True if at least one face is detected.
    """
    if not FACE_DETECTION_AVAILABLE:
        return True  # Default to keep image if OpenCV not available

    # Load Haar cascade for face detection
    if cascade_path is None:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"

    face_cascade = cv2.CascadeClassifier(cascade_path)

    # Read image
    image = cv2.imread(str(image_path))
    if image is None:
        print(f"  Warning: Could not read image {image_path}")
        return True  # Keep unreadable images

    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Detect faces
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))

    return len(faces) > 0


def folderize_images():
    """Main function to process images and move those without faces."""

    if not FACE_DETECTION_AVAILABLE:
        print("\n❌ OpenCV is required for face detection.")
        print("   Install it with: pip install opencv-python")
        print("\n   Alternatively, use a custom cascade file.\n")
        return

    current_dir = Path.cwd()
    no_face_dir = current_dir / "no_face"

    # Create no_face directory if it doesn't exist
    no_face_dir.mkdir(exist_ok=True)
    print(f"📁 Created/Using directory: {no_face_dir}\n")

    # Walk through all files recursively
    image_count = 0
    no_face_count = 0
    moved_count = 0

    for root, dirs, files in os.walk(current_dir):
        root_path = Path(root)

        # Skip the no_face directory to avoid processing moved files
        if root_path == no_face_dir:
            continue

        for file in files:
            file_path = root_path / file

            if not is_image_file(file):
                continue

            image_count += 1
            print(f"📷 Processing: {file_path.relative_to(current_dir)}")

            # Check if image has a face
            try:
                has_face = has_human_face(file_path)
            except Exception as e:
                print(f"  ⚠️ Error processing: {e}")
                continue

            if not has_face:
                no_face_count += 1

                # Create relative path structure in no_face folder
                relative_path = file_path.relative_to(current_dir)
                destination = no_face_dir / relative_path

                # Create subdirectories if needed
                destination.parent.mkdir(parents=True, exist_ok=True)

                # Move the file
                try:
                    shutil.move(str(file_path), str(destination))
                    print(f"  🚫 Moved to no_face/{relative_path}")
                    moved_count += 1
                except Exception as e:
                    print(f"  ❌ Failed to move: {e}")
            else:
                print(f"  ✅ Has face - keeping in place")

    # Print summary
    print("\n" + "=" * 50)
    print("📊 SUMMARY")
    print("=" * 50)
    print(f"Total images processed: {image_count}")
    print(f"Images without faces: {no_face_count}")
    print(f"Images moved to 'no_face': {moved_count}")
    print(f"Images with faces (kept): {image_count - no_face_count}")

    if moved_count > 0:
        print(f"\n📁 Moved images to: {no_face_dir}")
    print("=" * 50)


if __name__ == "__main__":
    print("🔍 Face Detection Image Organizer")
    print("=" * 50)
    print("Processing images in:", Path.cwd())
    print("Images with faces will stay in place")
    print("Images WITHOUT faces will be moved to 'no_face/'")
    print("=" * 50 + "\n")

    response = input("Continue? (y/n): ").lower().strip()
    if response == "y":
        folderize_images()
    else:
        print("Operation cancelled.")
