
import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from dotenv import load_dotenv

load_dotenv()

PREFIX = "keda-load-test-"


class Spacelift:
    def __init__(self):
        self.endpoint = os.environ["SPACELIFT_ENDPOINT"]
        self.session = requests.Session()
        self.token = self.authenticate()

    def graphql(self, query, variables=None, authenticated=True):
        headers = {}
        if authenticated:
            headers["Authorization"] = f"Bearer {self.token}"

        response = self.session.post(
            self.endpoint,
            json={"query": query, "variables": variables or {}},
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()

        if result.get("errors"):
            raise RuntimeError(result["errors"])

        return result["data"]

    def authenticate(self):
        query = """
        mutation ($id: ID!, $secret: String!) {
          apiKeyUser(id: $id, secret: $secret) {
            jwt
          }
        }
        """
        data = self.graphql(
            query,
            {
                "id": os.environ["SPACELIFT_API_KEY_ID"],
                "secret": os.environ["SPACELIFT_API_KEY_SECRET"],
            },
            authenticated=False,
        )
        return data["apiKeyUser"]["jwt"]

    def stacks(self):
        data = self.graphql("""
        query {
          stacks {
            id
            name
          }
        }
        """)
        return data["stacks"]

    def schema(self):
        data = self.graphql("""
        query {
          __schema {
            mutationType {
              fields {
                name
                args {
                  name
                  type {
                    kind
                    name
                    ofType {
                      kind
                      name
                      ofType {
                        name
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """)
        fields = data["__schema"]["mutationType"]["fields"]
        for field in fields:
            if field["name"] in (
                "stackCreate",
                "stackUpdate",
                "runTrigger",
                "stackDelete",
            ):
                print(field)

    def create_stack(self, index):
        name = f"{PREFIX}{index:03d}"

        query = """
        mutation ($input: StackInput!) {
          stackCreate(input: $input) {
            id
            name
          }
        }
        """

        stack_input = {
            "name": name,
            "description": "KEDA autoscaling load test",
            "namespace": os.environ["GITHUB_NAMESPACE"],
            "repository": os.environ["GITHUB_REPOSITORY"],
            "branch": "main",
            "projectRoot": "workload",
            "space": os.getenv("SPACELIFT_SPACE_ID", "root"),
            "workerPool": os.environ["SPACELIFT_WORKER_POOL_ID"],
            "autodeploy": False,
            "labels": ["keda-load-test"],
        }

        return self.graphql(
            query, {"input": stack_input}
        )["stackCreate"]

    def trigger(self, stack_id):
        query = """
        mutation ($stackId: ID!) {
          runTrigger(stack: $stackId) {
            id
            state
          }
        }
        """
        return self.graphql(
            query, {"stackId": stack_id}
        )["runTrigger"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=["schema", "list", "create", "trigger"]
    )
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()

    api = Spacelift()

    if args.command == "schema":
        api.schema()
        return

    if args.command == "list":
        for stack in api.stacks():
            if stack["id"].startswith(PREFIX):
                print(stack)
        return

    if args.command == "create":
        if not 1 <= args.count <= 50:
            parser.error("--count must be between 1 and 50")

        existing = {s["name"] for s in api.stacks()}

        for i in range(1, args.count + 1):
            name = f"{PREFIX}{i:03d}"
            if name in existing:
                print(f"Skipping {name}")
                continue

            result = api.create_stack(i)
            print(f"Created {result['id']}")
            time.sleep(0.3)
        return

    if args.command == "trigger":
        stacks = [
            s for s in api.stacks()
            if s["id"].startswith(PREFIX)
        ][:args.count]

        if not stacks:
            raise RuntimeError("No test stacks found")

        if not 1 <= args.concurrency <= 10:
            parser.error("--concurrency must be between 1 and 10")

        print(f"Triggering {len(stacks)} stacks")

        def submit(stack):
            # Separate client/session for each thread.
            client = Spacelift()
            return stack["id"], client.trigger(stack["id"])

        with ThreadPoolExecutor(
            max_workers=args.concurrency
        ) as executor:
            futures = [
                executor.submit(submit, stack)
                for stack in stacks
            ]

            for future in as_completed(futures):
                try:
                    stack_id, run = future.result()
                    print(f"{stack_id}: {run['id']} ({run['state']})")
                except Exception as exc:
                    print(f"Trigger failed: {exc}")


if __name__ == "__main__":
    main()
