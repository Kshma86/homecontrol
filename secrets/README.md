# HomeControl encrypted secrets bundle

Ez a konyvtar csak titkositott secrets bundle-t tarolhat.

Gitbe/Gitea-ba mehet:

- `age-recipient.txt`
- `manifest.txt`
- `*.age`
- `*.age.sha256`

Gitbe/Gitea-ba nem mehet:

- age identity private key
- `.env`
- `secrets.yaml`
- SSH private key
- restic password
- nyers token vagy jelszo

Az elso beallitas:

```bash
cd /srv/docker/homecontrol
scripts/init_secrets_age_key.sh
sudo scripts/create_secrets_bundle.sh
```

Restore proba stagingbe:

```bash
cd /srv/docker/homecontrol
sudo scripts/restore_secrets_bundle.sh
```

Eles visszaallitas csak tiszta restore gepen:

```bash
cd /srv/docker/homecontrol
sudo scripts/restore_secrets_bundle.sh --apply --confirm
```
