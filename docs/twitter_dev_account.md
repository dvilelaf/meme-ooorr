
# How to obtain X API tokens

1. Visit [X developer dashboard](https://developer.x.com/en/portal/dashboard)  and login with you X account.

2. If this is the first time you visit this website, you will be offered different account tiers. Sign up for free account.

3. You will need to provide a short explanation on why you need API access. You can use ChatGPT with the following prompt:
    ```
    Write a short usecase description to submit an access request to Twitter developer API. The project is about an AI agent that engages with other agents.
    ```

4. Go to Dashboard -> Settings -> User authentication settings -> Set up

5. Select permissions to `Read and write and Direct message`

6. Select app type to `Web app, Automate App or Bot`

7. Put any website in both `Callback URI / Redirect URL` and `Website URL` fields. It has to look like `https://domain.com`

8. You will be given two tokens, `OAuth 2.0 Client ID` and `Client Secret`. You won't need those, but save them anyway.

9. Go to the `Keys and tokens` tab and generate all the five remaining tokens. You will get some from the `Consumer Keys` section and some from the `Authentication Tokens` section.

10. Fill in the .env file with the following variables:
    ```
    TWEEPY_CONSUMER_API_KEY=
    TWEEPY_CONSUMER_API_KEY_SECRET=
    TWEEPY_BEARER_TOKEN=
    TWEEPY_ACCESS_TOKEN=
    TWEEPY_ACCESS_TOKEN_SECRET=
    ```