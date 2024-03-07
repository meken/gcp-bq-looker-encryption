import argparse
import uuid

import tink

from google.cloud import bigquery

from tink import daead
from tink.integration import gcpkms


def encrypt_and_insert(project_id, dataset, table_name, cipher):
    client = bigquery.Client(project=project_id)
    table = client.get_table(f"{dataset}.{table_name}")

    rows_to_insert = [
        (uuid.uuid4().hex, cipher.encrypt_deterministically(b"alice", b"")),
        (uuid.uuid4().hex, cipher.encrypt_deterministically(b"bob", b"")),
        (uuid.uuid4().hex, cipher.encrypt_deterministically(b"charlie", b"")),
    ]

    errors = client.insert_rows(
        table, rows_to_insert, row_ids=bigquery.AutoRowIDs.GENERATE_UUID
    )

    return errors


def get_cipher(keyset_path, kek_uri):
    daead.register()
    with open(keyset_path, "r") as f:
        keyset = tink.JsonKeysetReader(f.read())
    
    keyset_handle = tink.KeysetHandle.read(
        keyset, gcpkms.GcpKmsClient(None, None).get_aead(kek_uri)
    )

    return keyset_handle.primitive(daead.DeterministicAead)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Encrypt and insert data into BigQuery"
    )
    parser.add_argument("--project-id", required=True, help="The GCP project ID")
    parser.add_argument("--dataset", required=True, help="The BigQuery dataset")
    parser.add_argument("--table-name", required=True, help="The BigQuery table name")
    parser.add_argument("--wrapped-key-path", required=True, help="The path to the wrapped key")
    parser.add_argument("--kek-uri", required=True, help="The KEK URI")
    args = parser.parse_args()

    cipher = get_cipher(args.wrapped_key_path, args.kek_uri)
    errors = encrypt_and_insert(args.project_id, args.dataset, args.table_name, cipher)
    if errors:
        print(errors)
    else:
        print("Inserted rows successfully")
