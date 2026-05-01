# How to Generate a GitHub Personal Access Token (PAT) for a Specific Repository

## 1. Sign in to GitHub

1. Open: [https://github.com](https://github.com)
2. Sign in to your account.

---

## 2. Open Developer Settings

1. Click your **profile picture** (top-right corner).
2. Select **Settings**.
3. Scroll to the bottom of the left sidebar.
4. Click **Developer settings**.

---

## 3. Open Personal Access Tokens

1. Click **Personal access tokens**.
2. Choose one of the following:

   * **Fine-grained tokens** (recommended)
   * **Tokens (classic)**

Use **Fine-grained tokens** when you want access limited to a specific repository.

---

# Option A — Fine-Grained Token (Recommended)

## 4. Create Token

1. Click **Generate new token**.
2. Select **Generate new token (fine-grained)**.

---

## 5. Configure Token

Fill the form:

**Token name**

Example:

```
repo-access-token
```

**Expiration**

Choose a duration such as:

```
30 days
90 days
Custom
```

---

## 6. Select Resource Owner

Choose:

```
Your GitHub username
```

or the organization that owns the repository.

---

## 7. Restrict Repository Access

Under **Repository access** select:

```
Only select repositories
```

Click **Select repositories** and choose the target repository.

Example:

```
my-org/my-repo
```

---

## 8. Set Repository Permissions

Grant the minimal permissions required.

Typical settings for Git operations:

| Permission    | Access                    |
| ------------- | ------------------------- |
| Contents      | Read and write            |
| Metadata      | Read                      |
| Pull requests | Read and write (optional) |

For **read-only cloning**, set:

```
Contents → Read-only
```

---

## 9. Generate Token

1. Click **Generate token**.
2. GitHub will display the token **once only**.

Example:

```
github_pat_xxxxxxxxxxxxxxxxxxxxxxxxx
```

---

## 10. Save the Token Securely

Store it in a password manager or environment variable.

Example:

```
export GITHUB_TOKEN=github_pat_xxxxxxxxxxxxxxxxxxxxxxxxx
```

---

# Using the Token

## Clone a Repository

```
git clone https://<TOKEN>@github.com/OWNER/REPO.git
```

Example:

```
git clone https://github_pat_xxx@github.com/my-org/my-repo.git
```

---

## Authenticate When Prompted

If Git asks for credentials:

```
Username: your-github-username
Password: <PASTE TOKEN>
```

---

# Option B — Classic Token (Legacy)

1. Go to **Developer settings → Personal access tokens → Tokens (classic)**.
2. Click **Generate new token**.
3. Choose scopes such as:

```
repo
workflow
read:org
```

4. Generate the token and store it securely.

Classic tokens have **broad access and cannot be limited to a single repository**.

---

# Best Practices

* Prefer **fine-grained tokens**.
* Use **minimum required permissions**.
* Set **short expiration dates**.
* Store tokens in a **secret manager or environment variables**.
* Revoke tokens when no longer needed.

---

# Revoking a Token

1. Go to **Settings → Developer settings → Personal access tokens**.
2. Locate the token.
3. Click **Revoke**.

---

# Verification

Test the token:

```
curl -H "Authorization: Bearer <TOKEN>" https://api.github.com/user
```

If valid, GitHub returns your account information.
