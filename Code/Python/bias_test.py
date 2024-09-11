import os
import sys
import random

# List of cognitive biases with intuitive questions and weightings
biases = {
    "Confirmation Bias": {
        "questions": [
            "Do you prefer hearing information that supports your existing opinions?",
            "When you see evidence that contradicts your view, do you tend to dismiss it quickly?"
        ],
        "weight": 1.5,
        "description": "This reflects a tendency to seek out information that confirms your pre-existing beliefs."
    },
    "Anchoring Bias": {
        "questions": [
            "When making decisions, do you rely heavily on the first piece of information you receive?",
            "Do you tend to hold on to your first opinion, even when new information becomes available?"
        ],
        "weight": 1.0,
        "description": "This evaluates how much your decisions rely on initial impressions."
    },
    "Availability Heuristic": {
        "questions": [
            "Do recent events make you think they are more likely to happen again?",
            "Do you feel that something is more likely to happen if it’s fresh in your memory?"
        ],
        "weight": 1.0,
        "description": "This checks whether recent events disproportionately influence your perception of likelihood."
    },
    "Hindsight Bias": {
        "questions": [
            "Do you often feel like an outcome was obvious after it has already happened?",
            "When a result occurs, do you tend to think you 'knew it all along'?"
        ],
        "weight": 1.2,
        "description": "This reflects a tendency to view past events as predictable after they happen."
    },
    "Overconfidence Bias": {
        "questions": [
            "Do you often feel very confident in your predictions, even when there is little evidence?",
            "Do you believe you’re better than most people at tasks, even when you have little experience?"
        ],
        "weight": 1.3,
        "description": "This evaluates how overconfident you are in your abilities or predictions."
    },
    "Sunk Cost Fallacy": {
        "questions": [
            "Do you keep working on something just because you’ve already put a lot of time or money into it?",
            "Do you avoid quitting a project or investment because of the effort you’ve already put in?"
        ],
        "weight": 1.2,
        "description": "This checks whether past investments (time, effort, or money) overly influence your future decisions."
    },
    "Framing Effect": {
        "questions": [
            "Does how something is presented affect how you feel about it?",
            "If told there’s a '90% success rate' versus a '10% failure rate,' does that change how you perceive it?"
        ],
        "weight": 1.2,
        "description": "This evaluates whether you are influenced by how information is presented, even when the facts are the same."
    },
    "Bandwagon Effect": {
        "questions": [
            "Do you find yourself adopting opinions or following trends just because a lot of people are doing the same?",
            "Do you tend to follow the group opinion, even if you're unsure about it?"
        ],
        "weight": 1.0,
        "description": "This checks how much you are influenced by the actions or opinions of others."
    },
    "Self-Serving Bias": {
        "questions": [
            "When things go well, do you attribute it to your own efforts, but when things go poorly, do you blame external factors?",
            "Do you feel you deserve more credit for your successes than others?"
        ],
        "weight": 1.3,
        "description": "This reflects how much you credit yourself for success while blaming others or circumstances for failures."
    },
    "Fundamental Attribution Error": {
        "questions": [
            "When someone makes a mistake, do you think it’s because of their personality, not the situation they were in?",
            "Do you often assume people act a certain way because of who they are, rather than considering the situation?"
        ],
        "weight": 1.1,
        "description": "This checks whether you blame others' actions on their character, while downplaying external circumstances."
    },
    "Halo Effect": {
        "questions": [
            "Do you assume someone who is good at one thing is also good at other unrelated things?",
            "If you like one thing about a person, do you tend to like everything about them?"
        ],
        "weight": 1.0,
        "description": "This evaluates how much you let a single positive trait influence your perception of other unrelated traits."
    },
    "Horn Effect": {
        "questions": [
            "If you dislike one thing about a person, do you assume they have other negative qualities?",
            "Do you find that a single bad trait makes you think negatively about a person overall?"
        ],
        "weight": 1.0,
        "description": "This reflects whether a negative impression of one trait leads you to view everything about a person negatively."
    },
    "Ingroup Bias": {
        "questions": [
            "Do you feel more comfortable with people who share similar backgrounds, beliefs, or interests?",
            "Do you trust people more if they are part of your own social group?"
        ],
        "weight": 1.2,
        "description": "This checks whether you favor people from your own social group over those from outside."
    },
    "Belief Bias": {
        "questions": [
            "Do you accept arguments more easily when they align with your existing beliefs?",
            "Do you tend to agree with conclusions just because they match your opinions?"
        ],
        "weight": 1.3,
        "description": "This evaluates whether you judge arguments based on their alignment with your existing beliefs, rather than logic."
    },
    "Negativity Bias": {
        "questions": [
            "Do negative events affect you more deeply than positive ones, even when the positives are more frequent?",
            "Do you tend to focus on the negatives in a situation, even when there are more positive aspects?"
        ],
        "weight": 1.1,
        "description": "This checks how much negative information influences you compared to positive information."
    },
    "Gambler's Fallacy": {
        "questions": [
            "Do you believe that if something has happened often, it’s less likely to happen in the future?",
            "Do you think that random events 'balance out' over time, like a coin toss?"
        ],
        "weight": 1.0,
        "description": "This evaluates whether you believe random events are influenced by previous occurrences."
    },
    "Status Quo Bias": {
        "questions": [
            "Do you prefer to keep things the way they are, even when change might be better?",
            "Are you uncomfortable with changes, even when they are small?"
        ],
        "weight": 1.2,
        "description": "This checks whether you favor the current state of affairs over potential improvements through change."
    },
    "Outcome Bias": {
        "questions": [
            "Do you judge decisions by their outcome, rather than by the reasoning behind them?",
            "If something turned out well, do you assume the decision was a good one, regardless of how it was made?"
        ],
        "weight": 1.1,
        "description": "This reflects how much you judge decisions based on their results rather than the quality of the decision-making process."
    },
    "Dunning-Kruger Effect": {
        "questions": [
            "Do you feel confident in your abilities, even when you have little experience in a given area?",
            "Do you underestimate how much others know compared to you?"
        ],
        "weight": 1.3,
        "description": "This checks whether you overestimate your own abilities or knowledge."
    },
    "Optimism Bias": {
        "questions": [
            "Do you believe that good things are more likely to happen to you than to others?",
            "Do you tend to downplay risks because you believe things will work out in the end?"
        ],
        "weight": 1.2,
        "description": "This reflects how much you expect positive outcomes, even when the risks are high."
    },
    "Pessimism Bias": {
        "questions": [
            "Do you tend to expect the worst, even when there's no strong reason to believe it?",
            "Do you assume bad outcomes are more likely, even when positive outcomes are possible?"
        ],
        "weight": 1.2,
        "description": "This checks whether you expect negative outcomes more often than is warranted by the situation."
    },
    "Survivorship Bias": {
        "questions": [
            "Do you focus on successful examples and ignore the failures when making decisions?",
            "Do you assume something is common or easy because successful examples are easy to find?"
        ],
        "weight": 1.0,
        "description": "This evaluates how much you are influenced by success stories while ignoring the likelihood of failure."
    },
    "Illusory Correlation": {
        "questions": [
            "Do you believe two things are related just because they happen together often?",
            "Do you see patterns where there may not be any?"
        ],
        "weight": 1.1,
        "description": "This checks whether you perceive connections between unrelated events."
    },
    "Recency Bias": {
        "questions": [
            "Do you place more importance on recent events than older, equally important ones?",
            "Do you think recent experiences are more meaningful than those that happened further in the past?"
        ],
        "weight": 1.1,
        "description": "This reflects how much recent events influence your decisions compared to older ones."
    },
    "Clustering Illusion": {
        "questions": [
            "Do you believe that random events happen in streaks or clusters?",
            "Do you tend to see patterns in random data, like thinking something is 'due' to happen?"
        ],
        "weight": 1.0,
        "description": "This evaluates whether you see patterns in random events where none actually exist."
    }
}
# Scoring system and corresponding answer map
score_map = {
    "Y": 2,
    "M": 1,
    "N": 0,
    "n": -1,
    "NO": -2
}

numeric_score_map = {
    1: "Y",  # Yes
    2: "M",  # Maybe Yes
    3: "N",  # Neutral
    4: "n",  # Maybe No
    5: "NO"  # No
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
        answer = int(input("Your answer: ").strip())
    except ValueError:
        answer = 0
    
    while answer not in numeric_score_map:
        print("Invalid answer. Please respond with a number between 1 and 5.")
        try:
            answer = int(input("Your answer (1-5): ").strip())
        except ValueError:
            answer = 0
    
    return numeric_score_map[answer]

def interpret_score(overall_score):
    if overall_score > 20:
        return "Highly Biased: You exhibit a strong tendency toward cognitive biases across many categories."
    elif 10 <= overall_score <= 20:
        return "Moderately Biased: You show several cognitive biases, but not strongly in every category."
    elif 0 <= overall_score < 10:
        return "Slight Bias: You have some bias but remain relatively objective overall."
    elif -10 <= overall_score < 0:
        return "Unbiased: You exhibit minimal cognitive bias and are generally objective."
    elif overall_score < -10:
        return "Highly Unbiased: You demonstrate strong critical thinking and are resistant to common biases."
    else:
        return "Neutral: Your score suggests a balanced mindset with no clear indication of bias."

def test_for_bias():
    total_score = 0
    bias_scores = {}

    # Randomize order of biases and questions
    all_questions = []
    for bias_name, bias_data in biases.items():
        for question in bias_data["questions"]:
            all_questions.append((bias_name, question, bias_data["weight"]))

    random.shuffle(all_questions)

    total_questions_count = len(all_questions)
    current_question_number = 0

    for bias_name, question, weight in all_questions:
        answer_str = ask_question(question, current_question_number + 1, total_questions_count)
        score = score_map[answer_str]  # Convert answer string to corresponding integer score

        if bias_name not in bias_scores:
            bias_scores[bias_name] = 0

        bias_scores[bias_name] += score
        total_score += score * weight
        current_question_number += 1
        sys.stdout.flush()  # Ensure smooth output of progress bar

    # Test complete; clear terminal for results
    clear_terminal()

    # Display the overall score and its interpretation
    print(f"Overall Score: {total_score:.2f}")
    interpretation = interpret_score(total_score)
    print(f"Interpretation: {interpretation}")

    # Calculate bias score breakdown
    print("\n--- Detailed Report ---")
    for bias_name, bias_data in biases.items():
        bias_score = bias_scores.get(bias_name, 0)
        avg_score = bias_score / len(bias_data["questions"])
        print(f"\n{bias_name}:")
        print(f"  Average Score: {avg_score:.2f}")
        print(f"  {bias_data['description']}")
    
    # Text-based heatmap
    print("\n--- Heatmap ---")
    for bias_name, bias_data in biases.items():
        avg_score = bias_scores.get(bias_name, 0) / len(bias_data["questions"])
        heatmap = "#" * int((avg_score + 2) * 5) + "-" * (10 - int((avg_score + 2) * 5))
        print(f"{bias_name[:20].ljust(20)} | {heatmap} | Avg Score: {avg_score:.2f}")

# Run the test
if __name__ == "__main__":
    test_for_bias()
