/// The product's name, as people see it: window title, tray, notifications,
/// pairing screen. Native manifests (Info.plist, AndroidManifest, the
/// Windows and Linux runners, web/) carry the same value.
///
/// All of them are stamped from `shared/brand.json` by
/// `scripts/gen_brand.py` — edit the JSON and rerun the script, not this line.
const String appName = 'LifePete';

/// Where a person writes to reach the operator — the address PRIVACY.md
/// gives for deletion. Stamped from the same `shared/brand.json`.
const String contactEmail = 'ahmed.elghareeb@proton.me';
