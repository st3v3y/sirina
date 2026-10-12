export const site = {
  title: "Sirina — private meeting recorder for macOS (Windows & Linux in preview)",
  description:
    "Sirina records your calls, transcribes them on your own computer and summarizes them with a local AI model. macOS on Apple Silicon, with Windows and Linux in preview. No bots, no uploads, no account.",
  githubUrl: "https://github.com/st3v3y/sirina",
  coffeeUrl: "https://buymeacoffee.com/sirina.app",
  licenseUrl: "https://polyformproject.org/licenses/noncommercial/1.0.0/",
  version: "0.2",
  showBetaBar: true,
  // Flip to true once a GitHub release with a .dmg exists: the download buttons then point
  // to the latest release instead of the build-from-source instructions.
  hasRelease: true,
};

export const issuesUrl = `${site.githubUrl}/issues`;
export const downloadUrl = site.hasRelease
  ? `${site.githubUrl}/releases/latest`
  : `${site.githubUrl}#installation`;
export const downloadLabel = site.hasRelease ? "Download beta for macOS" : "Install from source";
