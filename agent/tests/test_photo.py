import random

from PIL import Image

from app import photo


def make_img(path, seed, exif=None, size=(128, 128)):
    rnd = random.Random(seed)
    img = Image.new("RGB", size)
    # blocky random scene so perceptual hashes differ between seeds
    px = img.load()
    for bx in range(0, size[0], 16):
        for by in range(0, size[1], 16):
            c = (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
            for x in range(bx, bx + 16):
                for y in range(by, by + 16):
                    px[x, y] = c
    if exif is not None:
        img.save(path, exif=exif)
    else:
        img.save(path)
    return str(path)


def make_exif(lat, lng, taken="2026:10:20 10:00:00"):
    ex = Image.Exif()
    ex[0x8825] = {1: "N" if lat >= 0 else "S", 2: (abs(lat), 0, 0), 3: "E" if lng >= 0 else "W", 4: (abs(lng), 0, 0)}
    ex[0x0132] = taken
    return ex


TICKET = {"lat": 12.97, "lng": 77.59, "closed_at": "2026-10-21T09:00:00Z"}


def test_reused_photo_is_flagged(tmp_path):
    idx = photo.PhotoIndex(str(tmp_path / "idx.json"))
    a = make_img(tmp_path / "a.jpg", 1)
    idx.add("other-ticket", photo.hashes(photo.load_image(a)))
    ev = photo.verify_photo("this-ticket", a, TICKET, idx)
    assert ev.verdict == "contradicts_fix" and "duplicate" in ev.details["flags"]
    assert ev.likelihood_ratio >= photo.LR_DUPLICATE


def test_distinct_photo_with_matching_exif_supports_fix(tmp_path):
    idx = photo.PhotoIndex(str(tmp_path / "idx.json"))
    idx.add("other-ticket", photo.hashes(photo.load_image(make_img(tmp_path / "o.jpg", 1))))
    p = make_img(tmp_path / "p.jpg", 2, make_exif(12.97, 77.59))
    ev = photo.verify_photo("this-ticket", p, TICKET, idx)
    assert ev.verdict == "supports_fix" and ev.likelihood_ratio < 1
    assert set(ev.details["passed"]) == {"duplicate", "location", "timestamp"}


def test_far_location_and_stale_timestamp_are_flagged(tmp_path):
    idx = photo.PhotoIndex(str(tmp_path / "idx.json"))
    p = make_img(tmp_path / "p.jpg", 3, make_exif(18.52, 73.85, taken="2026:05:01 10:00:00"))
    ev = photo.verify_photo("this-ticket", p, TICKET, idx)
    assert set(ev.details["flags"]) == {"location", "timestamp"}
    assert ev.likelihood_ratio == photo.LR_GPS_FAR * photo.LR_STALE


def test_no_exif_no_index_is_inconclusive(tmp_path):
    idx = photo.PhotoIndex(str(tmp_path / "idx.json"))
    ev = photo.verify_photo("this-ticket", make_img(tmp_path / "p.jpg", 4), TICKET, idx)
    assert ev.verdict == "inconclusive" and ev.likelihood_ratio == 1.0


def test_haversine_known_distance():
    # one degree of latitude is about 111.2 km
    assert abs(photo.haversine_m(0, 0, 1, 0) - 111195) < 200


def test_photo_hashes_are_remembered_so_a_later_ticket_is_flagged(tmp_path):
    """No manual index.add: verify_photo itself must record each closure photo."""
    idx = photo.PhotoIndex(str(tmp_path / "idx.json"))
    a = make_img(tmp_path / "a.jpg", 7)
    first = photo.verify_photo("ticket-1", a, TICKET, idx)
    assert "duplicate" not in first.details["flags"]
    second = photo.verify_photo("ticket-2", a, TICKET, photo.PhotoIndex(str(tmp_path / "idx.json")))
    assert "duplicate" in second.details["flags"]
    # re-checking the same ticket is not a duplicate of itself
    again = photo.verify_photo("ticket-1", a, TICKET, photo.PhotoIndex(str(tmp_path / "idx.json")))
    assert again.details["checks"]["duplicate"]["nearest_ticket"] == "ticket-2"


def test_evidence_with_a_nearest_neighbour_serialises_to_json(tmp_path):
    """imagehash distances are numpy ints; the Evidence must still dump to JSON (it is stored and streamed)."""
    idx = photo.PhotoIndex(str(tmp_path / "idx.json"))
    photo.verify_photo("t1", make_img(tmp_path / "a.jpg", 1), TICKET, idx)
    ev = photo.verify_photo("t2", make_img(tmp_path / "b.jpg", 2), TICKET, idx)
    assert isinstance(ev.details["checks"]["duplicate"]["hamming"], int)
    assert ev.model_dump_json()
