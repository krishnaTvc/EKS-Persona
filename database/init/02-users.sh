#!/bin/bash
set -eu

# Official MySQL runs this after the schema, on a new data volume only.
# generate-passwords.py generates hexadecimal passwords, so no SQL quoting is needed here.
registration_password="$(cat /run/secrets/registration_password)"
persona_password="$(cat /run/secrets/persona_password)"
for value in "$registration_password" "$persona_password"; do
    if [[ ! "$value" =~ ^[a-f0-9]{48}$ ]]; then
        echo 'Invalid application password file. Generate it with scripts/cloud/generate-passwords.py.' >&2
        exit 1
    fi
done

MYSQL_PWD="$(cat /run/secrets/mysql_root_password)" mysql --protocol=socket -uroot <<SQL
CREATE USER 'registration'@'%' IDENTIFIED BY '$registration_password';
GRANT SELECT, INSERT ON animal_persona.registrations TO 'registration'@'%';
CREATE USER 'persona_reader'@'%' IDENTIFIED BY '$persona_password';
GRANT SELECT ON animal_persona.persona TO 'persona_reader'@'%';
SQL
unset registration_password persona_password value
