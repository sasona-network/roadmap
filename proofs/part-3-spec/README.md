# Part 3, step 1: the question, written down

How a member tests a service, written down as rules anyone can implement.

## What was built

[`sasona-protocol` version 0.3.0](https://github.com/sasona-network/sasona-protocol/blob/a89850c201887549c6bef21a2b3de72d980ae3bb/SPEC.md), section 2:

- **The question.** A fresh random nonce becomes a small program whose right answer only the member knows. The question is one exact sequence of bytes, so it has one hash.
- **The order.** The question's hash goes on chain before the service is called. The nonce is revealed afterwards, with the reply's hash and the verdict.
- **The verdict.** `delivered` if the answer is in the reply, `wrong_answer` if it is not, `empty` if nothing came back. Anyone holding the reply can run this again.
- **What a reading proves, and what it does not.** This is stated plainly in 2.6. The question was fixed first, and the record agrees with itself. But the member alone holds the reply, and the service does not sign it, so a reading is still the member's word until the second readings of part 4 and the stakes of part 5.

## Check it yourself

[`vectors/question.json`](https://github.com/sasona-network/sasona-protocol/blob/a89850c201887549c6bef21a2b3de72d980ae3bb/vectors/question.json) holds 3 questions with their exact bytes and hashes, 11 replies with their verdicts, 4 nonces that must be refused, and 9 questions that look the same but are not fair. The Python and the Rust implementation match all of it, and so does the program: a test pins its question to these values.

```bash
python reference/check.py
cd rust && cargo test
```

## How it was checked

An independent review of the first draft found:

- **The member decides the verdict alone,** and the spec claimed more than that. 2.6 now says so.
- **The question was sent to the service in full,** and it contains the answer, so an echo would pass. Only the code goes now.
- **Nonce reuse was forbidden but not enforced.** The program now records every nonce.
- **The fairness check accepted `true` where it wanted `1`.** It now compares exact bytes.
- **`delivered` claimed the code was run.** It only shows the answer came back, and the spec now says that.
