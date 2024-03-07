# BQ Column Level Encryption and Looker

This repository is intended as an example of how to encrypt sensitive data in BigQuery and use it in Looker.

## Terminology

**DEK** (Data Encryption Key) — this is the key that is used for encrypting & decrypting the sensitive data and needs to be kept secret.

**KEK** (Key Encryption Key) — this is the key that is used to for encrypting and decrypting the DEK, not the data. Stored securely in [Cloud Key Management Service (KMS)](https://cloud.google.com/kms/docs/key-management-service) and can only be accessed by specific users (configured through IAM permissions).

**Wrapped key** — this is the DEK encrypted by the KEK. No need to keep it secret as you need access to the KEK to decrypt it.

## Setting up the KEK

Assuming that you have the correct set of permissions, you can create a key-ring and then add a key to it.

```shell
REGION=...
KEYRING=...
KEY_NAME=...
gcloud kms keyrings create $KEYRING --location=$REGION
gcloud kms keys create $KEY_NAME --location=$REGION --keyring=$KEYRING --purpose=encryption
```

## Generating the wrapped key

There are multiple ways of doing this, but we'll use the `tinkey` utility for that. Follow the instructions [here](https://developers.google.com/tink/install-tinkey) to install it. Once it's installed run the following command to generate the wrapped key. This is a one-off process.

```shell
KEK_URI=`gcloud kms keys describe --location=$REGION --keyring=$KEYRING $KEYNAME --format="value(name)"`
tinkey create-keyset \
    --key-template AES256_SIV \
    --out-format json \
    --out wrapped_key.json \
    --master-key-uri "$KEK_URI"
```

## Using the wrapped key for encyrption

Now we've got the wrapped key, we can use it to encrypt the sensitive data. This could be a stand alone application running on premises (as long KMS is accesible) or a service running in the cloud (Dataflow jobs, Cloud Functions). 

In this example we've prepared a sample Python script that you can run from the Cloud Shell. Before you run it, make sure that there's a BigQuery dataset & table:

```shell
PROJECT_ID=
BQ_DATASET=...
BQ_TABLE=...
bq mk --location=$REGION --dataset $PROJECT_ID:$BQ_DATASET
bq mk --table $PROJECT_ID:$BQ_DATASET.$BQ_TABLE id:STRING,name:BYTES
```

Once the table is there, you can insert some encrypted sample data:

```shell
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python encrypt.py \
    --project $PROJECT_ID \
    --dataset $BQ_DATASET \
    --table $BQ_TABLE \
    --wrapped-key-path wrapped_key.json \
    --kek-uri $KEK_URI
```

In order to view the encrypted data you can run a SQL query:

```shell
$ bq query --use_legacy_sql=false "SELECT * FROM \`${PROJECT_ID}.${BQ_DATASET}.${BQ_TABLE}\`"
+----------------------------------+------------------------------------------+
|                id                |                   name                   |
+----------------------------------+------------------------------------------+
| fa3c595da17c4efbb73d5c87c8a2ef77 |     AWAgxHgBiS+/UweRFgjRkBeOhIlvROv8Wbs= |
| bc631aa12c2d441bbe044f2185e8a1fe |         AWAgxHi9A0PoraW9TINwTg2QqzAKZLTz |
| 682802ae73194789a81ed7dba0fafb65 | AWAgxHgtS5DrHe0FHRxfJMchE/b0OVy+HBAEVg== |
+----------------------------------+------------------------------------------+
```

## Accessing the data in Looker

In order to see the data in cleartext in Looker, you need to use the AEAD functions from BigQuery in the dimension definition. Before you do that, store the KEK uri and the wrapped key contents (as bytes) as constants in your `manifest.lkml`.

```lookml
constant: key_resource_uri {
  value: "gcp-kms://projects/.../locations/.../keyRings/.../cryptoKeys/..."
}
constant: wrapped_key {
  value: "\n$\x00\x9c\xdaB\xda...."
}
```

Once these have been defined, in your `view` file, you can reference them (note that we're passing the wrapped key content as a byte literal to BigQuery, hence the `b` prefix before the reference to the wrapped key):

```lookml
dimension: name {
    type: string
    sql: 
        DETERMINISTIC_DECRYPT_STRING(
            KEYS.KEYSET_CHAIN(
                "@{key_resource_uri}", 
                b"@{wrapped_key}"
            ),
            ${TABLE}.name,
            ""
        ) ;;
}
```

Make sure that the Looker service account that's accessing BigQuery has the _Cloud KMS CryptoKey Decrypter Via Delegation_ role.

Now when the contents for the `name` column are displayed, the data will be decrypted using the wrapped key and the KEK.