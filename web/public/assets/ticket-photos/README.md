# Ticket photos

Cards in the triage queue, approvals and "My tickets" show a photo when one is known for the ticket, and say
"No photo on record" otherwise. Nothing is generated or guessed.

Photo sources, in order:
1. The Engine's demo set: the twelve `DEMO-*` tickets have a real "as reported" photo (open licence, see
   `demo/photos/ATTRIBUTION.md`). These need no entry here.
2. Entries in `index.json` in this folder.

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
