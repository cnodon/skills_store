#!/usr/bin/env node

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import { spawnSync } from "node:child_process";

const ROOT_DIR = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const SOURCES_PATH = path.join(ROOT_DIR, "official_sources.json");
const INDEX_PATH = path.join(ROOT_DIR, "index.json");
const SKILLS_DIR = path.join(ROOT_DIR, "skills");
const DIST_DIR = path.join(ROOT_DIR, "dist");
const CACHE_DIR = path.join(ROOT_DIR, ".cache");

const args = new Set(process.argv.slice(2));
const SHOULD_COMMIT = args.has("--commit");
const SHOULD_PUSH = args.has("--push");
const VERBOSE = args.has("--verbose");

function log(message, extra) {
  if (extra !== undefined) {
    console.log(`[sync] ${message}`, extra);
  } else {
    console.log(`[sync] ${message}`);
  }
}

function debug(message, extra) {
  if (!VERBOSE) return;
  log(message, extra);
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function removeDirContents(dirPath) {
  ensureDir(dirPath);
  for (const entry of fs.readdirSync(dirPath)) {
    fs.rmSync(path.join(dirPath, entry), { recursive: true, force: true });
  }
}

function run(command, commandArgs, options = {}) {
  debug(`${command} ${commandArgs.join(" ")}`);
  const result = spawnSync(command, commandArgs, {
    cwd: options.cwd,
    encoding: "utf8",
    stdio: options.stdio ?? "pipe"
  });
  if (result.status !== 0) {
    const stderr = result.stderr?.trim();
    const stdout = result.stdout?.trim();
    throw new Error(
      `${command} failed (${result.status})${stderr ? `: ${stderr}` : stdout ? `: ${stdout}` : ""}`
    );
  }
  return result.stdout?.trim() ?? "";
}

function repoSlugFromUrl(repoUrl) {
  const trimmed = repoUrl.trim().replace(/\.git$/, "").replace(/\/$/, "");
  const sshMatch = trimmed.match(/^git@[^:]+:(.+)$/);
  if (sshMatch) return sshMatch[1];
  const url = new URL(trimmed);
  const parts = url.pathname.split("/").filter(Boolean);
  if (parts.length < 2) {
    throw new Error(`Cannot derive repo slug from ${repoUrl}`);
  }
  return `${parts[parts.length - 2]}/${parts[parts.length - 1]}`;
}

function branchName(source) {
  return source.branch || "main";
}

function publisherPrefix(source) {
  return (source.publisher || source.id || "source")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function listFilesRecursively(dirPath) {
  const results = [];
  for (const entry of fs.readdirSync(dirPath, { withFileTypes: true })) {
    if (entry.name === ".git" || entry.name === ".DS_Store") continue;
    const absPath = path.join(dirPath, entry.name);
    if (entry.isDirectory()) {
      results.push(...listFilesRecursively(absPath));
    } else {
      results.push(absPath);
    }
  }
  return results;
}

function findSkillFiles(repoDir) {
  return listFilesRecursively(repoDir).filter((filePath) => path.basename(filePath) === "SKILL.md");
}

function extractFrontmatter(content) {
  if (!content.startsWith("---\n")) {
    return { metadata: {}, body: content };
  }
  const endIndex = content.indexOf("\n---", 4);
  if (endIndex === -1) {
    return { metadata: {}, body: content };
  }
  const raw = content.slice(4, endIndex).trim();
  const body = content.slice(endIndex + 4).trimStart();
  const metadata = {};
  for (const line of raw.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const idx = trimmed.indexOf(":");
    if (idx === -1) continue;
    const key = trimmed.slice(0, idx).trim();
    let value = trimmed.slice(idx + 1).trim();
    value = value.replace(/^['"]|['"]$/g, "");
    metadata[key] = value;
  }
  return { metadata, body };
}

function detectLicenseType(skillDir) {
  const candidates = ["LICENSE.txt", "LICENSE", "license.txt", "license"];
  for (const name of candidates) {
    const licensePath = path.join(skillDir, name);
    if (!fs.existsSync(licensePath)) continue;
    const text = fs.readFileSync(licensePath, "utf8");
    if (/Apache License/i.test(text)) return { file: name, type: "Apache-2.0" };
    if (/MIT License/i.test(text)) return { file: name, type: "MIT" };
    if (/Proprietary/i.test(text) || /source-available/i.test(text)) {
      return { file: name, type: "Source-Available" };
    }
    return { file: name, type: "Custom" };
  }
  return null;
}

function shouldSkipSkill(relativeSkillDir) {
  const normalized = relativeSkillDir.replace(/\\/g, "/");
  if (normalized === "template") return true;
  return false;
}

function preferredSourcePath(relativeSkillDir) {
  const normalized = relativeSkillDir.replace(/\\/g, "/");
  return normalized.replace(/^skills\//, "");
}

function candidateSlug(relativeSkillDir) {
  const normalized = preferredSourcePath(relativeSkillDir)
    .replace(/^\.curated\//, "")
    .replace(/^\.system\//, "")
    .replace(/^\.experimental\//, "")
    .replace(/^\./, "");
  return normalized.replace(/[\\/]+/g, "-").replace(/[^a-zA-Z0-9-]+/g, "-").replace(/-+/g, "-").replace(/^-+|-+$/g, "");
}

function sanitizeSlug(value) {
  return value.replace(/[^a-zA-Z0-9-]+/g, "-").replace(/-+/g, "-").replace(/^-+|-+$/g, "");
}

function buildUniqueSkillId(source, relativeSkillDir, usedIds) {
  const prefix = publisherPrefix(source);
  const base = sanitizeSlug(`${prefix}-${candidateSlug(relativeSkillDir)}`);
  if (!usedIds.has(base)) {
    usedIds.add(base);
    return base;
  }
  const withBucket = sanitizeSlug(`${prefix}-${preferredSourcePath(relativeSkillDir).replace(/[\\/]+/g, "-")}`);
  if (!usedIds.has(withBucket)) {
    usedIds.add(withBucket);
    return withBucket;
  }
  let i = 2;
  while (usedIds.has(`${withBucket}-${i}`)) i += 1;
  const unique = `${withBucket}-${i}`;
  usedIds.add(unique);
  return unique;
}

function copySkillDir(sourceDir, targetDir) {
  fs.cpSync(sourceDir, targetDir, {
    recursive: true,
    force: true,
    filter: (src) => {
      const name = path.basename(src);
      return name !== ".git" && name !== ".DS_Store";
    }
  });
}

function hashFile(filePath) {
  const hash = crypto.createHash("sha256");
  hash.update(fs.readFileSync(filePath));
  return hash.digest("hex");
}

function zipSkill(skillId, version) {
  const fileName = `${skillId}-${version}.zip`;
  const targetPath = path.join(DIST_DIR, fileName);
  fs.rmSync(targetPath, { force: true });
  run("zip", ["-rq", targetPath, skillId], { cwd: SKILLS_DIR });
  return {
    fileName,
    absolutePath: targetPath,
    sha256: hashFile(targetPath)
  };
}

function deriveRawZipUrl(repoSlug, branch, fileName) {
  return `https://raw.githubusercontent.com/${repoSlug}/${branch}/dist/${fileName}`;
}

function normalizeDescription(value, fallback) {
  return (value || fallback || "").replace(/\s+/g, " ").trim();
}

function buildDisplayName(source, skillName) {
  return `${source.publisher} ${skillName}`
    .replace(/[-_]+/g, " ")
    .replace(/\b\w/g, (m) => m.toUpperCase());
}

function currentTimestamp() {
  return new Date().toISOString();
}

function discoverSourceSkills(source, repoDir, sourceCommit, repoSlug, usedIds) {
  const discovered = [];
  for (const skillMdPath of findSkillFiles(repoDir)) {
    const skillDir = path.dirname(skillMdPath);
    const relativeSkillDir = path.relative(repoDir, skillDir);
    if (shouldSkipSkill(relativeSkillDir)) continue;

    const raw = fs.readFileSync(skillMdPath, "utf8");
    const { metadata, body } = extractFrontmatter(raw);
    const license = detectLicenseType(skillDir);
    if (!license) {
      debug(`Skipping ${relativeSkillDir} because no license file was found`);
      continue;
    }

    const skillId = buildUniqueSkillId(source, relativeSkillDir, usedIds);
    const shortCommit = sourceCommit.slice(0, 7);
    const version = metadata.version ? String(metadata.version) : `snapshot-${shortCommit}`;
    const name = metadata.name || path.basename(skillDir);
    const description = normalizeDescription(metadata.description, body.split("\n")[0]);
    discovered.push({
      id: skillId,
      name,
      displayName: buildDisplayName(source, name),
      description,
      version,
      publisher: source.publisher,
      publisherTrust: source.kind === "official" ? "official" : source.kind,
      skillType: "prompt",
      sourceRepo: source.repo,
      sourceRepoSlug: repoSlug,
      sourcePath: relativeSkillDir.replace(/\\/g, "/"),
      sourceCommit,
      mirrorPath: `skills/${skillId}`,
      licenseType: license.type,
      licenseFile: license.file,
      sourceDir: skillDir
    });
  }
  return discovered.sort((a, b) => a.id.localeCompare(b.id));
}

function writeMetaJson(skillDir, entry) {
  const meta = {
    id: entry.id,
    name: entry.name,
    displayName: entry.displayName,
    version: entry.version,
    publisher: entry.publisher,
    publisherTrust: entry.publisherTrust,
    description: entry.description,
    sourceRepo: entry.sourceRepo,
    sourcePath: entry.sourcePath,
    sourceCommit: entry.sourceCommit,
    mirrorPath: entry.mirrorPath,
    licenseFile: entry.licenseFile,
    licenseType: entry.licenseType,
    status: "active"
  };
  fs.writeFileSync(path.join(skillDir, "meta.json"), `${JSON.stringify(meta, null, 2)}\n`);
}

function mirrorSkills(discovered, repoBranch) {
  const timestamp = currentTimestamp();
  const indexSkills = [];
  for (const entry of discovered) {
    const targetDir = path.join(SKILLS_DIR, entry.id);
    copySkillDir(entry.sourceDir, targetDir);
    writeMetaJson(targetDir, entry);
    const zip = zipSkill(entry.id, entry.version);

    indexSkills.push({
      id: entry.id,
      name: entry.name,
      displayName: entry.displayName,
      description: entry.description,
      version: entry.version,
      publisher: entry.publisher,
      publisherTrust: entry.publisherTrust,
      skillType: entry.skillType,
      sourceRepo: entry.sourceRepo,
      sourcePath: entry.sourcePath,
      sourceCommit: entry.sourceCommit,
      mirrorPath: entry.mirrorPath,
      zipUrl: deriveRawZipUrl(entry.sourceRepoSlug === "cnodon/skills_store" ? entry.sourceRepoSlug : inferStoreRepoSlug(), repoBranch, zip.fileName),
      sha256: zip.sha256,
      licenseType: entry.licenseType,
      status: "active",
      updatedAt: timestamp
    });
  }
  return indexSkills;
}

function inferStoreRepoSlug() {
  const remoteUrl = run("git", ["remote", "get-url", "origin"], { cwd: ROOT_DIR });
  return repoSlugFromUrl(remoteUrl);
}

function refreshRepo(source) {
  ensureDir(CACHE_DIR);
  const repoSlug = repoSlugFromUrl(source.repo);
  const safeDir = repoSlug.replace(/[\\/]+/g, "__");
  const repoDir = path.join(CACHE_DIR, safeDir);

  if (!fs.existsSync(repoDir)) {
    log(`Cloning ${repoSlug}`);
    run("git", ["clone", "--depth", "1", "--branch", branchName(source), source.repo, repoDir]);
  } else {
    log(`Refreshing ${repoSlug}`);
    run("git", ["fetch", "--depth", "1", "origin", branchName(source)], { cwd: repoDir });
    run("git", ["checkout", branchName(source)], { cwd: repoDir });
    run("git", ["reset", "--hard", `origin/${branchName(source)}`], { cwd: repoDir });
    run("git", ["clean", "-fd"], { cwd: repoDir });
  }

  const commit = run("git", ["rev-parse", "HEAD"], { cwd: repoDir });
  return { repoDir, repoSlug, commit };
}

function writeIndex(indexSkills) {
  const payload = {
    version: 1,
    generatedAt: currentTimestamp(),
    skills: indexSkills.sort((a, b) => a.id.localeCompare(b.id))
  };
  fs.writeFileSync(INDEX_PATH, `${JSON.stringify(payload, null, 2)}\n`);
}

function maybeCommit() {
  if (!SHOULD_COMMIT && !SHOULD_PUSH) return;
  run("git", ["add", "skills", "dist", "index.json"], { cwd: ROOT_DIR });
  const status = run("git", ["status", "--short"], { cwd: ROOT_DIR });
  if (!status) {
    log("No changes to commit.");
  } else {
    run("git", ["commit", "-m", "sync official skills"], { cwd: ROOT_DIR });
    log("Created commit: sync official skills");
  }
}

function maybePush() {
  if (!SHOULD_PUSH) return;
  run("git", ["push", "origin", "main"], { cwd: ROOT_DIR, stdio: "inherit" });
}

function main() {
  if (!fs.existsSync(SOURCES_PATH)) {
    throw new Error(`Missing ${SOURCES_PATH}`);
  }

  const sources = readJson(SOURCES_PATH).sources.filter((source) => source.enabled !== false);
  if (sources.length === 0) {
    throw new Error("No enabled sources found in official_sources.json");
  }

  ensureDir(SKILLS_DIR);
  ensureDir(DIST_DIR);
  ensureDir(CACHE_DIR);
  removeDirContents(SKILLS_DIR);
  removeDirContents(DIST_DIR);

  const usedIds = new Set();
  const discovered = [];
  for (const source of sources) {
    const { repoDir, repoSlug, commit } = refreshRepo(source);
    const skills = discoverSourceSkills(source, repoDir, commit, repoSlug, usedIds);
    log(`Discovered ${skills.length} skills from ${repoSlug}`);
    discovered.push(...skills);
  }

  const repoBranch = run("git", ["branch", "--show-current"], { cwd: ROOT_DIR }) || "main";
  const indexSkills = mirrorSkills(discovered, repoBranch);
  writeIndex(indexSkills);

  log(`Mirrored ${indexSkills.length} skills into ${path.relative(process.cwd(), ROOT_DIR)}`);
  maybeCommit();
  maybePush();
}

try {
  main();
} catch (error) {
  console.error(`[sync] ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
}
