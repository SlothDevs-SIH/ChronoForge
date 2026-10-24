# Ticket photos

Cards in the triage queue, approvals and "My tickets" show a photo when one is known for the ticket, and say
"No photo on record" otherwise.

Photo sources, in order:
1. The Engine's demo set: the twelve `DEMO-*` tickets have a real "as reported" photo (open licence, see
   `demo/photos/ATTRIBUTION.md`). These need no entry here.
2. Entries in `photos` in `index.json` in this folder (one ticket, one photo of that ticket).
3. `categories` in `index.json`: a **synthetic** stand-in image per complaint category (pothole, garbage, streetlight, drain), for real tickets whose source data has no photo. The files `synthetic-*.jpg` are AI-generated, not photos of any real site; the card labels them "Synthetic image, not a photo of this site" and the badge reads "... record, synthetic image". They are never used as evidence. No water-leak or "other" image exists yet, so those tickets still say "No photo on file". To add variety, add more files to a category's list; a ticket always gets the same one.

## Adding a photo for a ticket

1. Copy the image here, named after the ticket (for example `blr-20739126.jpg`). JPEG or WebP, about 1200 px wide or less.
2. Add an entry to `photos` in `index.json`:

```json
"blr-20739126": {
  "file": "blr-20739126.jpg",
  "kind": "citizen",
  "alt": "Pothole on the road outside the ward office",
  "credit": "Photo submitted by the citizen with the complaint"
}
```

`kind` is one of:
- `citizen`: a photo the citizen really submitted with this complaint.
- `field`: a photo taken at the site for this ticket by a person, not the citizen.
- `illustrative`: a stand-in that does not show this exact spot. The card labels it "Illustrative photo".

Use `credit` for the source or licence. The card shows the kind next to the photo so nobody mistakes an illustration for
evidence.
