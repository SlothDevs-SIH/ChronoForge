# Notice: derived from our earlier GEOAI-04 project

This package reuses ideas and conventions from our own earlier project **GEOAI-04** (Fusion hackathon entry, a Sentinel-2 change-detection engine; repository `SlothDevs-SIH/GEOAI_04_SLOTHDEV`):

- reading only a small window of each Sentinel-2 band from the public cloud-optimised GeoTIFFs;
- deciding the reflectance DN offset **from the pixels**, because the item metadata is not reliable for some scenes;
- the invalid scene-classification classes (0, 1, 3, 8, 9, 10) used to mask cloud, shadow and no-data;
- the spectral index definitions (NDVI, NDBI, NDWI) and the lesson that vegetation change is seasonal.

We did **not** use its learned Siamese U-Net. That model was trained on urban construction change (OSCD) and its own README reports weak results in 3 of 10 test locations and many false alarms on farmland, so it is not valid evidence for "was this dump site cleared".

**New in this repository, built during the hackathon:** the ticket wiring, same-tile before/after scene selection around a complaint's creation and closing dates, matched-control comparison, abstention rules, the likelihood-ratio mapping, caching, and the validation (placebo and injected-change tests).
