package za.co.topprivateplug;

/** The exact advertised choices supplied by the service owner. */
final class PlanCatalog {
    static final class Plan { final int gigabytes,rand,days; Plan(int g,int r,int d){gigabytes=g;rand=r;days=d;} }
    static final Plan[] PLANS={new Plan(50,30,7),new Plan(100,50,30),new Plan(135,80,30),new Plan(200,120,30)};
}

