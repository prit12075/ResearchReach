from professor_finder import ProfessorFinderSystem
import sys
import os

def main():
    print("Starting Professor Finder System...")
    print("=" * 50)
    
    # Initialize system
    finder = ProfessorFinderSystem()
    
    # Sample student profile
    student = {
        'name': 'Sarah Johnson',
        'university': 'University of California, Berkeley',
        'year': 'Junior',
        'research_area': 'Machine Learning in Healthcare',
        'project': 'Developing ML models for early disease detection',
        'interest': 'Medical AI and predictive modeling',
        'contact': 'sarah.johnson@email.com'
    }
    
    # Research interests
    interests = ['Machine Learning', 'Healthcare AI', 'Medical Data Analysis']
    
    print(f"Student Profile: {student['name']}")
    print(f"Research Interests: {', '.join(interests)}")
    print("=" * 50)
    
    try:
        # Run the full process
        results = finder.run_full_process(student, interests)
        
        print(f"\nProcess completed successfully!")
        print(f"Found {len(results)} matching professors")
        
        # Display results
        for i, prof in enumerate(results, 1):
            print(f"\n{i}. {prof['name']}")
            print(f"   University: {prof['university']}")
            print(f"   Department: {prof['department']}")
            print(f"   Email: {prof['email']}")
            print(f"   Research Areas: {', '.join(prof['research_areas'])}")
            print(f"   Publications: {prof['publication_count']}")
            
    except Exception as e:
        print(f"Error occurred: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
