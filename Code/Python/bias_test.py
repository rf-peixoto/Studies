import os
import sys

# List of cognitive biases with intuitive questions and weightings
biases = {
    "Confirmation Bias": {
        "questions": [
            "Do you tend to look for information that supports your beliefs?",
            "Do you dismiss evidence that contradicts your opinions?"
        ],
        "weight": 1.5,
        "description": "You may focus on confirming your beliefs and ignore contradictory information."
    },
    "Anchoring Bias": {
        "questions": [
            "When making decisions, do you focus heavily on the first piece of information you see?",
            "Do you rely on initial information even when new data becomes available?"
        ],
        "weight": 1.0,
        "description": "You might rely too much on initial information when making decisions."
    },
    "Availability Heuristic": {
        "questions": [
            "Do recent events affect how you perceive the likelihood of future events?",
            "Do you believe something is more likely to happen if you can easily remember an example?"
        ],
        "weight": 1.0,
        "description": "You may overestimate the likelihood of events based on recent memories."
    },
    "Hindsight Bias": {
        "questions": [
            "Do you often feel that an outcome was obvious after it has already happened?",
            "When you see the result of an event, do you feel like you knew it all along?"
        ],
        "weight": 1.2,
        "description": "You may believe you predicted an outcome after it occurred, though you did not."
    },
    "Overconfidence Bias": {
        "questions": [
            "Do you often feel very confident in your opinions, even without much evidence?",
            "Do you think you're better at things than most people?"
        ],
        "weight": 1.3,
        "description": "You may have excessive confidence in your abilities or decisions."
    },
    "Sunk Cost Fallacy": {
        "questions": [
            "Do you continue with something because you've already invested time or money into it?",
            "Do you avoid quitting a project because you've already spent too much on it?"
        ],
        "weight": 1.2,
        "description": "You may be unwilling to stop an activity because of past investments, even if it no longer makes sense."
    },
    "Framing Effect": {
        "questions": [
            "Does the way something is presented change how you feel about it?",
            "If something is framed as a '90% success rate,' does that sound better than '10% failure rate'?"
        ],
        "weight": 1.2,
        "description": "You may be influenced by how information is framed, even when the facts are the same."
    },
    "Bandwagon Effect": {
        "questions": [
            "Do you tend to follow trends just because a lot of people are doing it?",
            "Do you often adopt the opinions of people around you?"
        ],
        "weight": 1.0,
        "description": "You may follow popular opinions or trends just because others are doing it."
    },
    "Self-Serving Bias": {
        "questions": [
            "Do you credit yourself when things go well but blame others or circumstances when things go wrong?",
            "Is it easier for you to see your successes than your failures?"
        ],
        "weight": 1.3,
        "description": "You may attribute success to your abilities and failures to external factors."
    },
    "Fundamental Attribution Error": {
        "questions": [
            "Do you often think someone’s behavior is due to their personality rather than their situation?",
            "Do you judge people’s actions without considering their circumstances?"
        ],
        "weight": 1.1,
        "description": "You may overestimate personal factors and underestimate situational factors in others' behavior."
    },
    "Halo Effect": {
        "questions": [
            "Do you assume people are good at everything because they excel in one area?",
            "If you like one thing about a person, do you tend to like everything about them?"
        ],
        "weight": 1.0,
        "description": "You may let one positive trait influence your judgment of other unrelated traits."
    },
    "Horn Effect": {
        "questions": [
            "If you dislike one thing about a person, do you assume they have other negative qualities?",
            "Do you tend to see everything about a person negatively if they do one thing wrong?"
        ],
        "weight": 1.0,
        "description": "You may allow a single negative trait to influence your perception of unrelated traits."
    },
    "Ingroup Bias": {
        "questions": [
            "Do you trust people more if they are part of your social or cultural group?",
            "Do you feel more comfortable with people who share similar backgrounds or interests?"
        ],
        "weight": 1.2,
        "description": "You may prefer people who belong to your own group over outsiders."
    },
    "Belief Bias": {
        "questions": [
            "Do you accept arguments more easily when they align with your existing beliefs?",
            "Do you think arguments are valid just because you agree with their conclusions?"
        ],
        "weight": 1.3,
        "description": "You may judge arguments based on whether you agree with them, rather than their logic."
    },
    "Negativity Bias": {
        "questions": [
            "Do you focus more on negative experiences than positive ones?",
            "Do negative events impact you more than positive ones?"
        ],
        "weight": 1.1,
        "description": "You may give more importance to negative events than positive ones."
    },
    "Gambler's Fallacy": {
        "questions": [
            "Do you believe that if something happens frequently, it’s less likely to happen in the future?",
            "Do you think random events, like a coin toss, will 'even out' over time?"
        ],
        "weight": 1.0,
        "description": "You may believe that random events are influenced by past occurrences, even when they are not."
    },
    "Status Quo Bias": {
        "questions": [
            "Do you prefer things to stay the same, even when change might be better?",
            "Are you uncomfortable with changes, even when they are small?"
        ],
        "weight": 1.2,
        "description": "You may resist change, even when it might improve your situation."
    },
    "Outcome Bias": {
        "questions": [
            "Do you judge decisions by their outcome rather than the reasoning behind them?",
            "Do you think a decision was good just because it led to a positive result?"
        ],
        "weight": 1.1,
        "description": "You may judge decisions based on their outcomes, not the quality of the decision-making process."
    },
    "Dunning-Kruger Effect": {
        "questions": [
            "Do you feel confident about a subject even when you have limited knowledge?",
            "Do you underestimate how much others know compared to you?"
        ],
        "weight": 1.3,
        "description": "You may overestimate your abilities or knowledge in certain areas."
    },
    "Optimism Bias": {
        "questions": [
            "Do you generally believe that good things will happen to you?",
            "Do you tend to ignore risks because you assume things will work out?"
        ],
        "weight": 1.2,
        "description": "You may expect positive outcomes more often than is realistic."
    },
    "Pessimism Bias": {
        "questions": [
            "Do you tend to expect bad things to happen, even without evidence?",
            "Do you assume the worst in situations, even when positive outcomes are possible?"
        ],
        "weight": 1.2,
        "description": "You may expect negative outcomes more often than is realistic."
    },
    "Survivorship Bias": {
        "questions": [
            "Do you focus on successful examples and ignore those that failed?",
            "Do you tend to look at success stories and assume they are typical?"
        ],
        "weight": 1.0,
        "description": "You may give more attention to successful examples while ignoring the failures."
    },
    "Illusory Correlation": {
        "questions": [
            "Do you believe two things are related because they happen together, even if there’s no evidence?",
            "Do you see patterns where none exist?"
        ],
        "weight": 1.1,
        "description": "You may perceive connections between unrelated events."
    },
    "Recency Bias": {
        "questions": [
            "Do recent events influence your decisions more than older, equally important ones?",
            "Do you give more weight to the latest information when making decisions?"
        ],
        "weight": 1.1,
        "description": "You may give too much importance to recent events compared to past ones."
    },
    "Clustering Illusion": {
        "questions": [
            "Do you see patterns in random data, like believing certain events occur in streaks?",
            "Do you think random events happen in clusters more than they actually do?"
        ],
        "weight": 1.0,
        "description": "You may see patterns in things that are actually random."
    }
}

# Scoring system and corresponding answer map
score_map = {
    1: "Yes",
    2: "Maybe Yes",
    3: "Neutral",
    4: "Maybe No",
    5: "No"
}

numeric_score_map = {
    1: 2,
    2: 1,
    3: 0,
    4: -1,
    5: -2
}

def clear_terminal():
    # Clears the terminal screen for both Windows and Linux/Mac systems
    os.system('cls' if os.name == 'nt' else 'clear')

def display_progress(current, total):
    # Simple progress bar display
    progress = int((current / total) * 20)
    bar = "[" + "#" * progress + "-" * (20 - progress) + "]"
    print(f"Progress: {bar} {current}/{total} questions", end='')

def ask_question(question, current, total):
    clear_terminal()
    display_progress(current, total)
    print(f"\n\n{question}")
    print("Answer options: 1) Yes, 2) Maybe Yes, 3) Neutral, 4) Maybe No, 5) No")
    
    try:
        answer = int(input("Your answer (1-5): ").strip())
    except ValueError:
        answer = 0
    
    while answer not in numeric_score_map:
        print("Invalid answer. Please respond with a number between 1 and 5.")
        try:
            answer = int(input("Your answer (1-5): ").strip())
        except ValueError:
            answer = 0
    
    return numeric_score_map[answer]

def test_for_bias():
    total_score = 0
    total_questions = 0
    bias_scores = {}
    
    # Total number of questions
    total_questions_count = sum(len(bias['questions']) for bias in biases.values())
    
    current_question_number = 0

    for bias_name, bias_data in biases.items():
        bias_scores[bias_name] = 0
        questions = bias_data["questions"]
        weight = bias_data["weight"]
        
        for question in questions:
            score = ask_question(question, current_question_number + 1, total_questions_count)
            bias_scores[bias_name] += score
            total_score += score * weight
            current_question_number += 1
            sys.stdout.flush()  # Ensure smooth output of progress bar

    # Test complete; clear terminal for results
    clear_terminal()

    # Calculate bias score breakdown
    print("\n--- Bias Breakdown ---")
    for bias_name, bias_data in biases.items():
        bias_score = bias_scores[bias_name]
        questions = bias_data["questions"]
        avg_score = bias_score / len(questions)
        
        print(f"\n{bias_name}:")
        print(f"  Average Score: {avg_score:.2f}")
        print(f"  {bias_data['description']}")

    # Calculate overall bias score
    average_total_score = total_score / total_questions_count
    bias_level = "Low Bias"
    
    if average_total_score > 1.0:
        bias_level = "High Bias"
    elif 0.5 < average_total_score <= 1.0:
        bias_level = "Moderate Bias"
    elif -0.5 <= average_total_score <= 0.5:
        bias_level = "Neutral"
    elif -1.0 <= average_total_score < -0.5:
        bias_level = "Low Bias"
    else:
        bias_level = "No Bias"
    
    print("\n--- Overall Results ---")
    print(f"Your overall score is: {average_total_score:.2f}")
    print(f"Your bias level is: {bias_level}")
    print("--------------------")

# Run the test
if __name__ == "__main__":
    test_for_bias()
