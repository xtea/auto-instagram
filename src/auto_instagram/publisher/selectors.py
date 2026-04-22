"""All instagram.com selectors live here. When IG ships a UI change, this
is the only file that needs patching.

Rules:
- Prefer aria-label / role / visible text. Never class names.
- Keep fallbacks as alternatives the caller can iterate over.
"""
from __future__ import annotations

# Top navigation — "Create" / "New post" icon
CREATE_BUTTON_ALTERNATIVES = [
    'svg[aria-label="New post"]',
    'a[href="#"][role="link"]:has(svg[aria-label="New post"])',
    'div[role="button"]:has(svg[aria-label="New post"])',
]

# After clicking Create, a popover may surface "Post" vs "Story" vs "Reel".
# We explicitly pick the one matching the post type.
CREATE_SUBMENU_POST_ALTERNATIVES = [
    'a[role="link"]:has-text("Post")',
    'div[role="button"]:has-text("Post")',
]
CREATE_SUBMENU_REEL_ALTERNATIVES = [
    'a[role="link"]:has-text("Reel")',
    'div[role="button"]:has-text("Reel")',
]

# The Create modal's hidden file input accepts multi-files for carousel.
CREATE_FILE_INPUT = 'input[type="file"][accept*="image"], input[type="file"][accept*="video"], form[role="presentation"] input[type="file"]'

# Buttons inside the modal flow. Matched by visible text via getByRole.
MODAL_NEXT_BUTTON_TEXT = "Next"
MODAL_SHARE_BUTTON_TEXT = "Share"
MODAL_BACK_BUTTON_TEXT = "Back"

# "Select crop" / "Add more" affordances
MODAL_OPEN_CROP_ALTERNATIVES = [
    'svg[aria-label="Select crop"]',
]
MODAL_ADD_MORE_ALTERNATIVES = [
    'svg[aria-label="Open media gallery"]',
]

# Caption input
CAPTION_TEXTAREA_ALTERNATIVES = [
    'textarea[aria-label="Write a caption..."]',
    'div[aria-label="Write a caption..."][contenteditable="true"]',
]

# Reel-specific: after uploading a vertical video IG may show an "OK" confirm
# asking you to confirm share-to-reels. We just click Next through it.
REEL_OK_BUTTON_TEXT = "OK"

# After Share completes, IG routes to a "Your post has been shared" screen
# with a link back to feed. We detect by visible text.
POST_SHARED_TEXT_ALTERNATIVES = [
    "Your post has been shared.",
    "Your reel has been shared.",
    "Your photo has been shared.",
]
