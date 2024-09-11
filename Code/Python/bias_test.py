# List of cognitive biases with intuitive questions
biases = {
    "Confirmation Bias": [
        "When you have a belief about something, do you only look for information that supports your view?",
        "If someone disagrees with you, do you tend to ignore their arguments?"
    ],
    "Anchoring Bias": [
        "When shopping, do you focus on the first price you see, even if there are other prices?",
        "Do you rely on the first piece of information you're given when making decisions?"
    ],
    "Availability Heuristic": [
        "Do recent events easily influence your opinions on how often things happen?",
        "Do you think something is more likely to happen if you can easily remember it?"
    ],
    "Hindsight Bias": [
        "When something happens, do you often think you 'knew it all along'?",
        "After an outcome is clear, do you feel like it was obvious from the beginning?"
    ],
    "Overconfidence Bias": [
        "Do you believe you are better at tasks than most people, even without much evidence?",
        "Do you often feel very sure about your decisions, even when others disagree?"
    ],
    "Sunk Cost Fallacy": [
        "Do you stick with something (like a project or relationship) just because you've already invested time or money in it?",
        "When you spend a lot on something, do you feel like you have to continue using it, even if you don't need it?"
    ],
    "Framing Effect": [
        "If something is described as a '90% success rate,' does it seem better than '10% failure rate'?",
        "Do you think how information is presented changes how you feel about it, even if the facts stay the same?"
    ],
    "Bandwagon Effect": [
        "Do you tend to follow trends just because a lot of people are doing it?",
        "If a group of people agrees on something, do you often go along with them?"
    ],
    "Self-Serving Bias": [
        "When things go well, do you often credit yourself, but blame external factors when things go wrong?",
        "Do you find it easier to see how others are responsible for problems than how you might be responsible?"
    ],
    "Fundamental Attribution Error": [
        "When someone does something wrong, do you often think it's because of their personality, not the situation?",
        "Do you judge people based on their actions without considering the circumstances they might be in?"
    ],
    "Halo Effect": [
        "If you like one thing about a person (like their appearance), do you assume other positive traits about them?",
        "Do you think people who are successful in one area are probably good in other areas too?"
    ],
    "Horn Effect": [
        "If you dislike one thing about a person, do you assume other negative traits about them?",
        "Do you think people who fail in one area are likely to fail in other areas as well?"
    ],
    "Ingroup Bias": [
        "Do you tend to trust people more if they are part of your social group?",
        "Do you prefer working with people who are similar to you?"
    ],
    "Belief Bias": [
        "If you already believe something is true, do you accept arguments supporting it without much thought?",
        "Do you find it easier to agree with arguments that align with your pre-existing beliefs?"
    ],
    "Negativity Bias": [
        "Do you focus more on negative events than positive ones, even if positive events are more common?",
        "Does one bad experience affect your opinion more than several good experiences?"
    ],
    "Gambler's Fallacy": [
        "If something happens frequently, do you think it is less likely to happen in the future?",
        "Do you believe a random event (like a coin toss) can 'balance out' over time?"
    ],
    "Status Quo Bias": [
        "Do you prefer things to stay the way they are, even when change might be better?",
        "Are you uncomfortable with changes, even small ones, in your daily routine?"
    ],
    "Outcome Bias": [
        "Do you judge a decision by its outcome, even if the decision was made for the right reasons?",
        "Do you think a decision was good just because things turned out well?"
    ],
    "Dunning-Kruger Effect": [
        "Do you often feel like you understand a subject well, even when you have little experience with it?",
        "Do you underestimate how much others know compared to you?"
    ],
    "Optimism Bias": [
        "Do you generally believe good things will happen to you, even if they don’t happen often?",
        "Do you tend to ignore potential risks because you think things will work out well?"
    ],
    "Pessimism Bias": [
        "Do you generally believe bad things will happen, even when there’s no strong reason to think so?",
        "Do you assume the worst in situations, even if positive outcomes are possible?"
    ],
    "Survivorship Bias": [
        "When looking at successful people or ideas, do you tend to ignore those that failed?",
        "Do you focus on success stories and assume they are typical?"
    ],
    "Illusory Correlation": [
        "Do you often think two unrelated things are connected because they happen at the same time?",
        "Do you see patterns where none exist (e.g., thinking wearing a 'lucky' item changes your outcomes)?"
    ],
    "Recency Bias": [
        "Do recent events influence your decisions more than older, equally important ones?",
        "Do you give more weight to the latest information when making decisions?"
    ],
    "Clustering Illusion": [
        "Do you believe random events happen in clusters more than they actually do?",
        "Do you see patterns in things that are actually random?"
    ]
}

# Scoring system
score_map = {
    "Yes": 2,
    "Maybe Yes": 1,
    "Neutral": 0,
    "Maybe No": -1,
    "No": -2
}

def ask_question(question):
    print(f"\n{question}")
    answer = input("Answer (Yes, Maybe Yes, Neutral, Maybe No, No): ").strip()
    while answer not in score_map:
        print("Invalid answer. Please respond with Yes, Maybe Yes, Neutral, Maybe No, or No.")
        answer = input("Answer (Yes, Maybe Yes, Neutral, Maybe No, No): ").strip()
    return score_map[answer]

def test_for_bias():
    total_score = 0
    total_questions = 0
    
    print("Starting bias test...\n")
    
    for bias, questions in biases.items():
        print(f"Testing for {bias}:")
        for question in questions:
            score = ask_question(question)
            total_score += score
            total_questions += 1
    
    # Calculate bias score
    average_score = total_score / total_questions
    bias_level = "Low Bias"
    
    if average_score > 1.0:
        bias_level = "High Bias"
    elif 0.5 < average_score <= 1.0:
        bias_level = "Moderate Bias"
    elif -0.5 <= average_score <= 0.5:
        bias_level = "Neutral"
    elif -1.0 <= average_score < -0.5:
        bias_level = "Low Bias"
    else:
        bias_level = "No Bias"
    
    print("\n--- Test Results ---")
    print(f"Total Score: {total_score}")
    print(f"Average Score: {average_score:.2f}")
    print(f"Bias Level: {bias_level}")
    print("--------------------")

# Run the test
if __name__ == "__main__":
    test_for_bias()
