"""LLM Skills - Focused knowledge injection for the LLM assistant.

Skills follow the standard folder/SKILL.md convention and now live PER-DOMAIN:
  data/domains/<domain_id>/skills/
    mlflow-run-interpretation/
      SKILL.md          # Required - main skill file with YAML frontmatter
      references/       # Optional - detailed docs loaded on demand
      scripts/          # Optional - executable validation scripts
      assets/           # Optional - templates, examples

Backward-compat: the legacy flat folder data/skills/ is still scanned and
its skills are tagged with domain_id='noted' (the platform Domain).

Skills are loaded on startup, registered in the system prompt,
and injected either statically (based on context triggers) or
dynamically (via the get_skill tool). When `active_domains` is supplied
to get_static_skills / get_registry_text, only skills whose domain_id is
in that list are considered.
"""

import os
import logging
import re

logger = logging.getLogger(__name__)

# Both layouts are scanned at startup; paths derived per-call from the data root.
_DATA_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data')
)
DOMAINS_DIR = os.path.join(_DATA_ROOT, 'domains')
LEGACY_SKILLS_DIR = os.path.join(_DATA_ROOT, 'skills')
LEGACY_DOMAIN_ID = 'noted'  # bucket pre-Domain-migration skills under 'noted'


class Skill:
    """A single skill loaded from a SKILL.md file."""
    __slots__ = ('name', 'description', 'triggers', 'priority', 'max_tokens',
                 'content', 'folder_path', 'domain_id')

    def __init__(self, name, description, triggers, priority, max_tokens,
                 content, folder_path, domain_id):
        self.name = name
        self.description = description
        self.triggers = triggers
        self.priority = priority
        self.max_tokens = max_tokens
        self.content = content
        self.folder_path = folder_path  # path to the skill folder
        self.domain_id = domain_id


class SkillRegistry:
    """Loads and manages the skill library."""

    def __init__(self, domains_dir=None, legacy_skills_dir=None):
        self._domains_dir = domains_dir or DOMAINS_DIR
        self._legacy_skills_dir = legacy_skills_dir or LEGACY_SKILLS_DIR
        self._skills = {}  # name -> Skill
        self._load_all()

    def _load_all(self):
        """Scan both the per-Domain layout and the legacy flat folder."""
        # 1) Per-Domain layout: data/domains/<domain_id>/skills/<skill>/SKILL.md
        domains_dir = os.path.abspath(self._domains_dir)
        if os.path.isdir(domains_dir):
            for domain_id in sorted(os.listdir(domains_dir)):
                domain_path = os.path.join(domains_dir, domain_id)
                if not os.path.isdir(domain_path):
                    continue
                skills_root = os.path.join(domain_path, 'skills')
                if not os.path.isdir(skills_root):
                    continue
                count = self._scan_skills_root(skills_root, domain_id)
                logger.info(
                    "Loaded %d skills from data/domains/%s/skills/",
                    count, domain_id,
                )
        else:
            logger.warning("Domains directory not found: %s", domains_dir)

        # 2) Legacy flat layout: data/skills/<skill>/SKILL.md
        # Pre-Domain skills (airflow-*, dvc-*, hydra-*, mlflow-*, etc.) -
        # bucket these under the 'noted' platform Domain so they only
        # surface when 'noted' is in active_domains.
        legacy_dir = os.path.abspath(self._legacy_skills_dir)
        if os.path.isdir(legacy_dir):
            count = self._scan_skills_root(legacy_dir, LEGACY_DOMAIN_ID)
            logger.info(
                "Loaded %d legacy skills from data/skills/ (assigned domain_id='%s')",
                count, LEGACY_DOMAIN_ID,
            )

    def _scan_skills_root(self, skills_root, domain_id):
        """Walk one skills/ directory and register each <skill>/SKILL.md."""
        count = 0
        for entry in sorted(os.listdir(skills_root)):
            entry_path = os.path.join(skills_root, entry)
            if not os.path.isdir(entry_path):
                continue
            skill_md = os.path.join(entry_path, 'SKILL.md')
            if not os.path.isfile(skill_md):
                continue
            try:
                skill = self._parse_skill(skill_md, entry_path, entry, domain_id)
                if not skill:
                    continue
                if skill.name in self._skills:
                    prev = self._skills[skill.name]
                    logger.warning(
                        "Skill name collision: '%s' redefined by domain '%s' "
                        "(previously from domain '%s'). Later registration wins; "
                        "names should be unique across Domains.",
                        skill.name, domain_id, prev.domain_id,
                    )
                self._skills[skill.name] = skill
                count += 1
            except Exception as e:
                logger.warning("Failed to load skill %s (%s): %s",
                               entry, domain_id, e)
        return count

    def _parse_skill(self, skill_md_path, folder_path, folder_name, domain_id):
        """Parse a SKILL.md file with YAML frontmatter."""
        with open(skill_md_path, 'r') as f:
            text = f.read()

        # Parse YAML frontmatter between --- markers
        match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', text, re.DOTALL)
        if not match:
            logger.warning("Skill %s/SKILL.md has no valid frontmatter", folder_name)
            return None

        frontmatter_text = match.group(1)
        content = match.group(2).strip()

        # Simple YAML parsing (avoid dependency on PyYAML for frontmatter)
        fm = {}
        for line in frontmatter_text.split('\n'):
            line = line.strip()
            if ':' in line:
                key, _, value = line.partition(':')
                key = key.strip()
                value = value.strip()
                # Handle list values [a, b, c]
                if value.startswith('[') and value.endswith(']'):
                    value = [v.strip().strip('"').strip("'")
                             for v in value[1:-1].split(',') if v.strip()]
                # Handle numeric values
                elif value.isdigit():
                    value = int(value)
                fm[key] = value

        name = fm.get('name', folder_name)
        description = fm.get('description', '')
        triggers = fm.get('triggers', [])
        if isinstance(triggers, str):
            triggers = [triggers]
        priority = fm.get('priority', 3)
        max_tokens = fm.get('max_tokens', 500)

        return Skill(name, description, triggers, priority, max_tokens,
                     content, folder_path, domain_id)

    def get_skill(self, name):
        """Get a skill by name. Returns the SKILL.md content string or None."""
        skill = self._skills.get(name)
        return skill.content if skill else None

    def get_skill_reference(self, skill_name, ref_path):
        """Load a reference file from a skill's references/ folder.

        Args:
            skill_name: The skill name (kebab-case)
            ref_path: Relative path within references/ (e.g., "common-errors.md")

        Returns:
            File content as string, or None if not found.
        """
        skill = self._skills.get(skill_name)
        if not skill:
            return None
        ref_file = os.path.join(skill.folder_path, 'references', ref_path)
        # Security: prevent path traversal
        ref_file = os.path.abspath(ref_file)
        if not ref_file.startswith(os.path.abspath(skill.folder_path)):
            logger.warning("Path traversal attempt in skill reference: %s", ref_path)
            return None
        if not os.path.isfile(ref_file):
            return None
        with open(ref_file, 'r') as f:
            return f.read()

    def get_skill_info(self, name):
        """Get full skill object by name."""
        return self._skills.get(name)

    def list_skills(self):
        """Return list of (name, metadata_dict) tuples for all skills."""
        return [(s.name, {
            "description": s.description,
            "triggers": s.triggers,
            "priority": s.priority,
            "max_tokens": s.max_tokens,
            "domain_id": s.domain_id,
        }) for s in sorted(self._skills.values(), key=lambda s: s.name)]

    def get_skill_meta(self, name):
        """Get metadata dict for a skill by name."""
        s = self._skills.get(name)
        if not s:
            return None
        return {
            "description": s.description,
            "triggers": s.triggers,
            "priority": s.priority,
            "max_tokens": s.max_tokens,
            "domain_id": s.domain_id,
        }

    def has_references(self, name):
        """Check if a skill has a references/ subfolder with files."""
        s = self._skills.get(name)
        if not s or not s.folder_path:
            return False
        refs_dir = os.path.join(s.folder_path, 'references')
        return os.path.isdir(refs_dir) and bool(os.listdir(refs_dir))

    def get_registry_text(self, active_domains=None):
        """Generate the skill registry text for the system prompt.

        Args:
            active_domains: optional list of domain_ids. When provided, only
                skills whose domain_id is in that list are listed. When None,
                all loaded skills are listed (legacy behavior).
        """
        lines = ["Available skills (use get_skill tool to load detailed instructions):"]
        for skill in sorted(self._skills.values(), key=lambda s: s.name):
            if active_domains is not None and skill.domain_id not in active_domains:
                continue
            lines.append(f"- {skill.name}: {skill.description}")
        return "\n".join(lines)

    def get_static_skills(self, context_conditions, active_domains=None):
        """Get priority-1 skills that match the given context conditions.

        Args:
            context_conditions: set of condition strings, e.g.
                {"mlflow_experiment_in_context", "notebook_cell_selected"}
            active_domains: optional list of domain_ids. When provided, only
                skills whose domain_id is in that list are considered. When
                None (legacy callers), no Domain filter is applied.

        Returns:
            List of (name, content) tuples for matching priority-1 skills.
            Respects max total token budget of ~32000 tokens.
        """
        matched = []
        total_tokens_est = 0
        max_budget = 32000  # hard cap for static skills; raises if exceeded

        for skill in self._skills.values():
            if skill.priority != 1:
                continue
            if not skill.triggers:
                continue
            if active_domains is not None and skill.domain_id not in active_domains:
                continue
            # Check if any trigger matches a context condition
            if any(t in context_conditions for t in skill.triggers):
                est_tokens = len(skill.content.split()) * 1.3  # rough estimate
                matched.append((skill.name, skill.content))
                total_tokens_est += est_tokens

        if total_tokens_est > max_budget:
            raise RuntimeError(
                f"Auto-injected priority-1 skills exceed {max_budget}-token budget "
                f"(estimated {int(total_tokens_est)} tokens across {len(matched)} skills: "
                f"{[name for name, _ in matched]}). Trim skill content or lower priority."
            )

        return matched


# Module-level singleton
_registry = None


def get_registry():
    """Get or create the global skill registry."""
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry
