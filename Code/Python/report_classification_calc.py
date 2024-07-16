from colorama import Fore, Style, init

init(autoreset=True)

def determine_source_reliability():
    print("Determine Source Reliability:")
    questions = [
        "Is there any doubt about the authenticity, trustworthiness, or competency of the source? (yes/no): ",
        "Has the source been reliable in the past? (yes/no): ",
        "Does the source have a history of providing accurate information? (yes/no): "
    ]

    answers = []
    for question in questions:
        answer = input(question).strip().lower()
        while answer not in ["yes", "no"]:
            print("Invalid input. Please answer with 'yes' or 'no'.")
            answer = input(question).strip().lower()
        answers.append(answer)

    if answers == ["no", "yes", "yes"]:
        return "A", "Completely Reliable"
    elif answers == ["no", "no", "yes"]:
        return "B", "Usually Reliable"
    elif answers == ["yes", "yes", "yes"]:
        return "C", "Fairly Reliable"
    elif answers == ["yes", "no", "no"]:
        return "D", "Not Usually Reliable"
    elif answers == ["yes", "yes", "no"]:
        return "E", "Unreliable"
    else:
        return "F", "Reliability Cannot Be Judged"

def determine_information_credibility():
    print("\nDetermine Information Credibility:")
    questions = [
        "Is the information confirmed by other independent sources? (yes/no): ",
        "Is the information logical in itself? (yes/no): ",
        "Is the information consistent with other information on the subject? (yes/no): ",
        "Does the information contradict any known facts? (yes/no): "
    ]

    answers = []
    for question in questions:
        answer = input(question).strip().lower()
        while answer not in ["yes", "no"]:
            print("Invalid input. Please answer with 'yes' or 'no'.")
            answer = input(question).strip().lower()
        answers.append(answer)

    if answers == ["yes", "yes", "yes", "no"]:
        return "1", "Confirmed"
    elif answers == ["no", "yes", "yes", "no"]:
        return "2", "Probably True"
    elif answers == ["no", "no", "yes", "no"]:
        return "3", "Possibly True"
    elif answers == ["no", "no", "no", "yes"]:
        return "4", "Doubtful"
    elif answers == ["yes", "no", "no", "yes"]:
        return "5", "Improbable"
    else:
        return "6", "Truth Cannot Be Judged"

def determine_tlp():
    print("\nDetermine Traffic Light Protocol (TLP):")
    questions = [
        "Is the information intended for public disclosure? (yes/no): ",
        "Is the information meant to be shared within a community? (yes/no): ",
        "Is the information meant to be shared only with individuals who need to know? (yes/no): ",
        "Does the information require strict handling with limited distribution? (yes/no): "
    ]

    answers = []
    for question in questions:
        answer = input(question).strip().lower()
        while answer not in ["yes", "no"]:
            print("Invalid input. Please answer with 'yes' or 'no'.")
            answer = input(question).strip().lower()
        answers.append(answer)

    if answers[0] == "yes":
        return "White", "Disclosure is not limited"
    elif answers[1] == "yes":
        return "Green", "Limited to the community"
    elif answers[2] == "yes" and answers[3] == "no":
        return "Amber", "Limited to individuals with a need to know"
    elif answers[2] == "yes" and answers[3] == "yes":
        return "Amber Strict", "Limited to individuals with a need to know; stricter handling than regular amber"
    else:
        return "Red", "Not for disclosure, restricted to participants only"

def get_color_for_reliability(reliability_code):
    colors = {
        "A": Fore.GREEN,
        "B": Fore.CYAN,
        "C": Fore.YELLOW,
        "D": Fore.MAGENTA,
        "E": Fore.RED,
        "F": Fore.WHITE
    }
    return colors.get(reliability_code, Fore.WHITE)

def get_color_for_credibility(credibility_code):
    colors = {
        "1": Fore.GREEN,
        "2": Fore.CYAN,
        "3": Fore.YELLOW,
        "4": Fore.MAGENTA,
        "5": Fore.RED,
        "6": Fore.WHITE
    }
    return colors.get(credibility_code, Fore.WHITE)

def get_color_for_tlp(tlp_code):
    colors = {
        "White": Fore.WHITE,
        "Green": Fore.GREEN,
        "Amber": Fore.YELLOW,
        "Amber Strict": Fore.LIGHTYELLOW_EX,
        "Red": Fore.RED
    }
    return colors.get(tlp_code, Fore.WHITE)

def main():
    print("NATO Grading System for Source Reliability and Information Credibility")

    source_reliability_code, source_reliability_desc = determine_source_reliability()
    info_credibility_code, info_credibility_desc = determine_information_credibility()
    tlp_code, tlp_desc = determine_tlp()

    source_color = get_color_for_reliability(source_reliability_code)
    credibility_color = get_color_for_credibility(info_credibility_code)
    tlp_color = get_color_for_tlp(tlp_code)

    print("\nFinal Rating:")
    print(f"Source Reliability: {source_color}{source_reliability_code} - {source_reliability_desc}{Style.RESET_ALL}")
    print(f"Information Credibility: {credibility_color}{info_credibility_code} - {info_credibility_desc}{Style.RESET_ALL}")
    print(f"NATO Rating: {source_color}{source_reliability_code}{credibility_color}{info_credibility_code}{Style.RESET_ALL}")
    print(f"TLP: {tlp_color}{tlp_code} - {tlp_desc}{Style.RESET_ALL}")

if __name__ == "__main__":
    main()
