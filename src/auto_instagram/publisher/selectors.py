"""All instagram.com selectors live here. When IG ships a UI change, this
is the only file that needs patching.

Rules:
- Prefer aria-label / role / visible text. Never class names.
- Keep fallbacks as alternatives the caller can iterate over.
"""
from __future__ import annotations

# Direct URL to the Create flow — much more reliable than clicking the
# sidebar "New post" button, which dispatches click via an internal React
# handler that resists synthetic clicks from Playwright.
CREATE_DIRECT_URL = "https://www.instagram.com/create/select/"

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

# Caption input. IG uses a Unicode ellipsis (…, U+2026) in the aria-label;
# partial-match selectors avoid that fragility.
CAPTION_TEXTAREA_ALTERNATIVES = [
    'textarea[aria-label^="Write a caption"]',
    'div[aria-label^="Write a caption"][contenteditable="true"]',
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
